"""Candlestick pattern detection (rule engine, deterministic).

Classic one-, two- and three-bar patterns as defined by Nison and catalogued by
Bulkowski (Encyclopedia of Candlestick Charts, 2008). Each detection carries its
trend context, because a reversal pattern only means something after a trend,
plus a volume check and whether it formed near a support/resistance level.

The research is sceptical: Marshall, Young & Rose (2006) find no value on US
large caps, while Caginalp & Laurent (1998) and Lu, Shiu & Liu (2012) find some
short-horizon value, more so in emerging retail-heavy markets. Treat candlesticks
as confirmation, never as a signal on their own.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TREND_BARS = 10      # bars used to judge the trend going into a pattern
LOOKBACK = 5         # report patterns completing in the last N bars

# Direction and type for every pattern. Reliability statistics are deliberately absent:
# Bulkowski's candlestick figures have not been verified for this table (see config notes).
PATTERNS = {
    "doji": ("neutral", "indecision"),
    "hammer": ("bullish", "reversal"),
    "inverted_hammer": ("bullish", "reversal"),
    "hanging_man": ("bearish", "reversal"),
    "shooting_star": ("bearish", "reversal"),
    "bullish_engulfing": ("bullish", "reversal"),
    "bearish_engulfing": ("bearish", "reversal"),
    "bullish_harami": ("bullish", "reversal"),
    "bearish_harami": ("bearish", "reversal"),
    "piercing_line": ("bullish", "reversal"),
    "dark_cloud_cover": ("bearish", "reversal"),
    "morning_star": ("bullish", "reversal"),
    "evening_star": ("bearish", "reversal"),
    "three_white_soldiers": ("bullish", "reversal"),
    "three_black_crows": ("bearish", "reversal"),
}


def _parts(o: float, h: float, l: float, c: float) -> tuple[float, float, float, float]:
    """Body size, upper shadow, lower shadow and full range of one candle."""
    body = abs(c - o)
    return body, h - max(o, c), min(o, c) - l, h - l


def prior_trend(close: np.ndarray, i: int, bars: int = TREND_BARS) -> str:
    """'up', 'down' or 'flat' for the ``bars`` closes before bar ``i`` (>3% move counts)."""
    if i - bars < 0:
        return "flat"
    change = (close[i - 1] - close[i - bars]) / close[i - bars]
    return "up" if change > 0.03 else "down" if change < -0.03 else "flat"


def _at(df: pd.DataFrame, i: int) -> tuple[float, float, float, float]:
    """Open, high, low, close of bar ``i``."""
    r = df.iloc[i]
    return float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"])


def patterns_at(df: pd.DataFrame, i: int) -> list[str]:
    """All candlestick patterns that complete on bar ``i``."""
    close = df["Close"].to_numpy()
    o, h, l, c = _at(df, i)
    body, up, low, rng = _parts(o, h, l, c)
    if rng <= 0:
        return []
    trend = prior_trend(close, i)
    avg_body = float(np.mean(np.abs(df["Close"].to_numpy()[max(0, i - 10):i] - df["Open"].to_numpy()[max(0, i - 10):i]))) or rng
    found = []

    if body <= 0.1 * rng:
        found.append("doji")
    small_top = up <= 0.3 * max(body, 1e-9) or up <= 0.1 * rng
    small_bottom = low <= 0.3 * max(body, 1e-9) or low <= 0.1 * rng
    if body > 0.1 * rng and low >= 2 * body and small_top:
        found.append("hammer" if trend == "down" else "hanging_man" if trend == "up" else None)
    if body > 0.1 * rng and up >= 2 * body and small_bottom:
        found.append("inverted_hammer" if trend == "down" else "shooting_star" if trend == "up" else None)

    if i >= 1:
        po, ph, pl, pc = _at(df, i - 1)
        pbody = abs(pc - po)
        bull, pbear = c > o, pc < po
        if trend == "down" and pbear and bull and o <= pc and c >= po and body > pbody:
            found.append("bullish_engulfing")
        if trend == "up" and pc > po and c < o and o >= pc and c <= po and body > pbody:
            found.append("bearish_engulfing")
        if trend == "down" and pbear and pbody > avg_body and max(o, c) < po and min(o, c) > pc and body < 0.5 * pbody:
            found.append("bullish_harami")
        if trend == "up" and pc > po and pbody > avg_body and max(o, c) < pc and min(o, c) > po and body < 0.5 * pbody:
            found.append("bearish_harami")
        if trend == "down" and pbear and pbody > avg_body and bull and o < pl and pc + pbody / 2 < c < po:
            found.append("piercing_line")
        if trend == "up" and pc > po and pbody > avg_body and c < o and o > ph and po < c < po + pbody / 2:
            found.append("dark_cloud_cover")

    if i >= 2:
        ao, _, _, ac = _at(df, i - 2)
        bo, _, _, bc = _at(df, i - 1)
        abody, bbody = abs(ac - ao), abs(bc - bo)
        t3 = prior_trend(close, i - 2)
        if t3 == "down" and ac < ao and abody > avg_body and bbody < 0.5 * abody and max(bo, bc) < ac \
                and c > o and c > (ao + ac) / 2:
            found.append("morning_star")
        if t3 == "up" and ac > ao and abody > avg_body and bbody < 0.5 * abody and min(bo, bc) > ac \
                and c < o and c < (ao + ac) / 2:
            found.append("evening_star")
        bars = [_at(df, j) for j in (i - 2, i - 1, i)]
        if t3 in ("down", "flat") and all(b[3] > b[0] and abs(b[3] - b[0]) > 0.6 * (b[1] - b[2]) for b in bars) \
                and bars[0][3] < bars[1][3] < bars[2][3] and all(bars[k][0] > bars[k - 1][0] for k in (1, 2)):
            found.append("three_white_soldiers")
        if t3 in ("up", "flat") and all(b[3] < b[0] and abs(b[3] - b[0]) > 0.6 * (b[1] - b[2]) for b in bars) \
                and bars[0][3] > bars[1][3] > bars[2][3] and all(bars[k][0] < bars[k - 1][0] for k in (1, 2)):
            found.append("three_black_crows")
    return [f for f in found if f]


def detect(df: pd.DataFrame, levels: list[dict] | None = None, atr: float | None = None,
           lookback: int = LOOKBACK) -> list[dict]:
    """Candlestick patterns completing in the last ``lookback`` bars, with trend, volume and S/R context."""
    out = []
    n = len(df)
    vol = df["Volume"].to_numpy()
    for i in range(max(2, n - lookback), n):
        names = patterns_at(df, i)
        if not names:
            continue
        o, h, l, c = _at(df, i)
        avg_vol = float(np.mean(vol[max(0, i - 20):i])) if i else float(vol[i])
        near = []
        if levels and atr:
            near = [f"{lv['type']} {lv['level']}" for lv in levels if min(abs(lv["level"] - l), abs(lv["level"] - h)) <= atr]
        for name in names:
            direction, kind = PATTERNS[name]
            out.append({
                "pattern": name,
                "date": str(df.index[i].date()),
                "bars_ago": n - 1 - i,
                "direction": direction,
                "type": kind,
                "prior_trend": prior_trend(df["Close"].to_numpy(), i),
                "volume_vs_avg20": round(float(vol[i] / avg_vol), 2) if avg_vol else None,
                "near_level": near,
                "reliability_note": "Bulkowski candlestick statistics not yet verified; treat as confirmation only",
            })
    return out
