"""Deterministic chart rule engine (spec §5).

Takes an OHLCV DataFrame and returns a JSON-safe dict of indicator values, trend
structure, support/resistance clusters, volume confirmation and detected
Bulkowski patterns with their reference statistics attached. The Chart Agent
only ever sees this output, never raw prices.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import candlesticks

STATS_PATH = Path(__file__).resolve().parents[3] / "config" / "bulkowski_stats.yaml"
REQUIRED_COLS = ["Open", "High", "Low", "Close", "Volume"]
MIN_BARS = 60
RECENT_BARS = 30      # a pattern's last pivot must fall within this many bars of today
MIN_SWING_PCT = 5.0   # floor for the zigzag swing size used by pattern detection


# ----------------------------------------------------------------- indicators

def sma(s: pd.Series, n: int) -> pd.Series:
    """Simple moving average over ``n`` bars."""
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    """Exponential moving average with span ``n``."""
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing: an EMA with alpha = 1/n."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index."""
    diff = close.diff()
    gain = _wilder(diff.clip(lower=0), n)
    loss = _wilder(-diff.clip(upper=0), n)
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(gain.notna())


def true_range(df: pd.DataFrame) -> pd.Series:
    """True range: the widest of high-low and the gaps from the prior close."""
    prev = df["Close"].shift()
    return pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    return _wilder(true_range(df), n)


def adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """Wilder's directional movement system: +DI, -DI and ADX."""
    up = df["High"].diff()
    down = -df["Low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = _wilder(true_range(df), n)
    plus_di = 100 * _wilder(plus_dm, n) / tr
    minus_di = 100 * _wilder(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": _wilder(dx, n)})


def parabolic_sar(df: pd.DataFrame, step: float = 0.02, max_af: float = 0.2) -> pd.Series:
    """Wilder's Parabolic SAR; returns the stop level for each bar."""
    high, low = df["High"].to_numpy(), df["Low"].to_numpy()
    n = len(df)
    sar = np.full(n, np.nan)
    if n < 2:
        return pd.Series(sar, index=df.index)
    long = high[1] >= high[0]
    ep = high[0] if long else low[0]
    sar[0] = low[0] if long else high[0]
    af = step
    for i in range(1, n):
        prev = sar[i - 1] + af * (ep - sar[i - 1])
        if long:
            prev = min(prev, low[i - 1], low[i - 2] if i > 1 else low[i - 1])
            if low[i] < prev:
                long, prev, ep, af = False, ep, low[i], step
            elif high[i] > ep:
                ep, af = high[i], min(af + step, max_af)
        else:
            prev = max(prev, high[i - 1], high[i - 2] if i > 1 else high[i - 1])
            if high[i] > prev:
                long, prev, ep, af = True, ep, high[i], step
            elif low[i] < ep:
                ep, af = low[i], min(af + step, max_af)
        sar[i] = prev
    return pd.Series(sar, index=df.index)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD line, signal line and histogram."""
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands: middle SMA and +/- k standard deviations."""
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return pd.DataFrame({"upper": mid + k * sd, "middle": mid, "lower": mid - k * sd})


# -------------------------------------------------------------------- pivots

@dataclass
class Pivot:
    """A swing high ('H') or swing low ('L') at bar index ``i``."""

    i: int
    price: float
    kind: str


def find_pivots(df: pd.DataFrame, window: int = 5) -> list[Pivot]:
    """Find swing highs/lows that are extremes within ``window`` bars on each side.

    Consecutive pivots of the same kind are collapsed to the more extreme one, so
    the result alternates H/L.
    """
    high, low = df["High"].to_numpy(), df["Low"].to_numpy()
    raw: list[Pivot] = []
    for i in range(window, len(df) - window):
        seg = slice(i - window, i + window + 1)
        if high[i] == high[seg].max():
            raw.append(Pivot(i, float(high[i]), "H"))
        elif low[i] == low[seg].min():
            raw.append(Pivot(i, float(low[i]), "L"))
    out: list[Pivot] = []
    for p in raw:
        if out and out[-1].kind == p.kind:
            better = p.price > out[-1].price if p.kind == "H" else p.price < out[-1].price
            if better:
                out[-1] = p
        else:
            out.append(p)
    return out


def significant_pivots(pivots: list[Pivot], min_swing_pct: float) -> list[Pivot]:
    """Zigzag filter: keep only swings of at least ``min_swing_pct`` between alternating pivots."""
    out: list[Pivot] = []
    for p in pivots:
        if not out:
            out.append(p)
        elif p.kind == out[-1].kind:
            if (p.price > out[-1].price) if p.kind == "H" else (p.price < out[-1].price):
                out[-1] = p
        elif abs(p.price - out[-1].price) / out[-1].price * 100 >= min_swing_pct:
            out.append(p)
    return out


def support_resistance(pivots: list[Pivot], price: float, tol: float, max_levels: int = 6) -> list[dict]:
    """Cluster pivot prices within ``tol`` into S/R levels; return the nearest supports and resistances."""
    clusters: list[list[float]] = []
    for p in sorted(pv.price for pv in pivots):
        if clusters and p - np.mean(clusters[-1]) <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = [
        {
            "level": round(float(np.mean(c)), 2),
            "touches": len(c),
            "type": "support" if np.mean(c) < price else "resistance",
            "distance_pct": round(float(100 * (np.mean(c) - price) / price), 2),
        }
        for c in clusters
    ]
    # Nearest levels on each side first; within that, more touches is stronger.
    per_side = max_levels // 2
    out = []
    for side in ("support", "resistance"):
        side_levels = [lv for lv in levels if lv["type"] == side]
        side_levels.sort(key=lambda lv: (abs(lv["distance_pct"]), -lv["touches"]))
        out += side_levels[:per_side]
    return out


# ------------------------------------------------------------------ patterns

@lru_cache(maxsize=1)
def bulkowski_stats() -> dict:
    """Load the reference pattern statistics table from config."""
    return yaml.safe_load(STATS_PATH.read_text(encoding="utf-8"))["patterns"]


def _pattern(df: pd.DataFrame, key: str, start: int, end: int, status: str, levels: dict) -> dict:
    """Build a pattern record with dates, key levels and its Bulkowski stats attached."""
    stats = bulkowski_stats()[key]
    return {
        "pattern": key,
        "name": stats["name"],
        "direction": stats["direction"],
        "status": status,
        "start": str(df.index[start].date()),
        "end": str(df.index[end].date()),
        "levels": {k: round(float(v), 2) for k, v in levels.items()},
        "bulkowski": {k: stats[k] for k in ("failure_rate_pct", "avg_move_pct", "frequency_rank", "source", "verified")},
    }


def _near(a: float, b: float, pct: float) -> bool:
    """True when ``a`` and ``b`` are within ``pct`` percent of their mean."""
    return abs(a - b) <= pct / 100 * (a + b) / 2


def detect_head_shoulders(df: pd.DataFrame, pivots: list[Pivot]) -> list[dict]:
    """Head-and-shoulders top and inverse (bottom) from the last five alternating pivots."""
    out, close = [], float(df["Close"].iloc[-1])
    for j in range(len(pivots) - 5, max(len(pivots) - 9, -1), -1):
        if j < 0:
            break
        a, b, c, d, e = pivots[j:j + 5]
        if e.i < len(df) - 1 - RECENT_BARS:
            break
        if not 0.5 <= (e.i - c.i) / max(c.i - a.i, 1) <= 2:  # shoulders roughly symmetric in time
            continue
        if a.kind == "H":
            ok = c.price > 1.03 * max(a.price, e.price) and _near(a.price, e.price, 5) and min(a.price, e.price) > max(b.price, d.price)
            key, broke = "head_shoulders_top", close < min(b.price, d.price)
        else:
            ok = c.price < 0.97 * min(a.price, e.price) and _near(a.price, e.price, 5) and max(a.price, e.price) < min(b.price, d.price)
            key, broke = "head_shoulders_bottom", close > max(b.price, d.price)
        if ok:
            neck = (b.price + d.price) / 2
            out.append(_pattern(df, key, a.i, e.i, "confirmed" if broke else "forming",
                                {"left_shoulder": a.price, "head": c.price, "right_shoulder": e.price, "neckline": neck}))
            break
    return out


def detect_double(df: pd.DataFrame, pivots: list[Pivot], min_gap: int = 10, depth_pct: float = 10) -> list[dict]:
    """Double top / double bottom: two similar extremes separated by a meaningful swing."""
    out, close = [], float(df["Close"].iloc[-1])
    for j in range(len(pivots) - 3, max(len(pivots) - 7, -1), -1):
        if j < 0:
            break
        a, mid, b = pivots[j:j + 3]
        if b.i < len(df) - 1 - RECENT_BARS:
            break
        if b.i - a.i < min_gap or not _near(a.price, b.price, 3):
            continue
        if a.kind == "H" and (min(a.price, b.price) - mid.price) / mid.price * 100 >= depth_pct:
            out.append(_pattern(df, "double_top", a.i, b.i, "confirmed" if close < mid.price else "forming",
                                {"peak_1": a.price, "peak_2": b.price, "confirmation": mid.price}))
            break
        if a.kind == "L" and (mid.price - max(a.price, b.price)) / mid.price * 100 >= depth_pct:
            out.append(_pattern(df, "double_bottom", a.i, b.i, "confirmed" if close > mid.price else "forming",
                                {"trough_1": a.price, "trough_2": b.price, "confirmation": mid.price}))
            break
    return out


def detect_triangle(df: pd.DataFrame, pivots: list[Pivot], flat_pct: float = 0.05) -> list[dict]:
    """Ascending / descending / symmetrical triangle from the last three highs and lows.

    Slopes are measured in percent of price per bar; under ``flat_pct`` counts as flat.
    """
    highs = [p for p in pivots if p.kind == "H"][-3:]
    lows = [p for p in pivots if p.kind == "L"][-3:]
    if len(highs) < 2 or len(lows) < 2:
        return []
    last = len(df) - 1
    if last - min(highs[0].i, lows[0].i) > 120 or last - max(highs[-1].i, lows[-1].i) > RECENT_BARS:
        return []

    def line(ps: list[Pivot]) -> tuple[float, float]:
        """Least-squares slope and intercept through pivot points."""
        m, c = np.polyfit([p.i for p in ps], [p.price for p in ps], 1)
        return float(m), float(c)

    mh, ch = line(highs)
    ml, cl = line(lows)
    price = float(df["Close"].iloc[-1])
    sh, sl = 100 * mh / price, 100 * ml / price
    upper, lower = mh * last + ch, ml * last + cl
    if upper <= lower:
        return []
    if abs(sh) < flat_pct and sl > flat_pct:
        key = "ascending_triangle"
    elif sh < -flat_pct and abs(sl) < flat_pct:
        key = "descending_triangle"
    elif sh < -flat_pct and sl > flat_pct:
        key = "symmetrical_triangle"
    else:
        return []
    status = "breakout_up" if price > upper else "breakout_down" if price < lower else "forming"
    start = min(highs[0].i, lows[0].i)
    return [_pattern(df, key, start, last, status, {"upper_line": upper, "lower_line": lower})]


def detect_flag(df: pd.DataFrame, pole_bars: int = 10, min_pole_pct: float = 10,
                max_flag_bars: int = 20, min_flag_bars: int = 5) -> list[dict]:
    """Bull/bear flag: a sharp pole followed by a tight, short consolidation."""
    close, high, low = df["Close"].to_numpy(), df["High"].to_numpy(), df["Low"].to_numpy()
    n = len(df)
    for flag_len in range(min_flag_bars, max_flag_bars + 1):
        p_end = n - 1 - flag_len
        p_start = p_end - pole_bars
        if p_start < 0:
            break
        move = (close[p_end] - close[p_start]) / close[p_start] * 100
        if abs(move) < min_pole_pct:
            continue
        f_hi, f_lo = high[p_end + 1:].max(), low[p_end + 1:].min()
        pole = abs(close[p_end] - close[p_start])
        if (f_hi - f_lo) > 0.5 * pole:
            continue
        slope = np.polyfit(range(flag_len), close[p_end + 1:], 1)[0]
        if move > 0 and slope <= 0 and f_lo > close[p_start] + 0.5 * pole:
            status = "breakout_up" if close[-1] > high[p_end + 1:-1].max() else "forming"
            return [_pattern(df, "bull_flag", p_start, n - 1, status,
                             {"pole_start": close[p_start], "pole_top": close[p_end], "flag_low": f_lo})]
        if move < 0 and slope >= 0 and f_hi < close[p_start] - 0.5 * pole:
            status = "breakout_down" if close[-1] < low[p_end + 1:-1].min() else "forming"
            return [_pattern(df, "bear_flag", p_start, n - 1, status,
                             {"pole_start": close[p_start], "pole_bottom": close[p_end], "flag_high": f_hi})]
    return []


def detect_cup_handle(df: pd.DataFrame, min_cup: int = 30, max_cup: int = 150,
                      depth: tuple[float, float] = (12, 35)) -> list[dict]:
    """Cup with handle: rounded U between two similar rims, then a shallow pullback handle."""
    close = df["Close"].to_numpy()
    n = len(close)
    for handle in range(5, 21):
        right = n - 1 - handle
        for cup in range(min_cup, min(max_cup, right) + 1, 5):
            left = right - cup
            lr, rr = close[left], close[right]
            if not _near(lr, rr, 5) or close[left:right + 1].max() > max(lr, rr) * 1.03:
                continue
            # Prior advance: the left rim caps a rise of at least 15% over the preceding 30 bars.
            pre = close[max(0, left - 30):left + 1]
            if left < 10 or pre.max() > lr * 1.01 or (lr - pre.min()) / pre.min() * 100 < 15:
                continue
            bottom_i = left + int(np.argmin(close[left:right + 1]))
            bottom = close[bottom_i]
            d = (min(lr, rr) - bottom) / min(lr, rr) * 100
            if not depth[0] <= d <= depth[1]:
                continue
            # U-shape: the low sits in the middle half and the base is not a single spike.
            if not left + cup * 0.25 <= bottom_i <= left + cup * 0.75:
                continue
            base = close[left + cup // 3: right - cup // 3]
            if (base < bottom + 0.35 * (min(lr, rr) - bottom)).mean() < 0.4:
                continue
            h = close[right + 1:]
            h_low = h.min()
            if not (h_low < rr and (rr - h_low) <= 0.5 * (rr - bottom) and h_low > bottom + 0.5 * (rr - bottom)):
                continue
            status = "breakout_up" if close[-1] > max(lr, rr) else "forming"
            return [_pattern(df, "cup_with_handle", left, n - 1, status,
                             {"left_rim": lr, "cup_bottom": bottom, "right_rim": rr, "handle_low": h_low})]
    return []


def detect_patterns(df: pd.DataFrame, pivots: list[Pivot]) -> list[dict]:
    """Run all five Bulkowski pattern families and return every detection."""
    return (detect_head_shoulders(df, pivots) + detect_double(df, pivots) + detect_triangle(df, pivots)
            + detect_flag(df) + detect_cup_handle(df))


# ----------------------------------------------------------------- assembly

def _r(x, nd: int = 2):
    """Round a scalar to ``nd`` places, mapping NaN to None for JSON."""
    return None if x is None or pd.isna(x) else round(float(x), nd)


def trend_structure(df: pd.DataFrame, adx_val: float | None) -> dict:
    """Classify trend from price vs SMA50/200, SMA50 slope and ADX strength."""
    close = df["Close"]
    s50, s200 = sma(close, 50), sma(close, 200)
    price = close.iloc[-1]
    slope50 = (s50.iloc[-1] - s50.iloc[-11]) / s50.iloc[-11] * 100 if len(df) >= 61 else np.nan
    above50 = bool(price > s50.iloc[-1]) if pd.notna(s50.iloc[-1]) else None
    above200 = bool(price > s200.iloc[-1]) if pd.notna(s200.iloc[-1]) else None
    if above50 and (above200 in (True, None)) and slope50 > 0:
        direction = "uptrend"
    elif above50 is False and (above200 in (False, None)) and slope50 < 0:
        direction = "downtrend"
    else:
        direction = "sideways"
    strength = "strong" if adx_val and adx_val >= 25 else "weak" if adx_val and adx_val < 20 else "moderate"
    return {
        "direction": direction,
        "strength": strength,
        "price_above_sma50": above50,
        "price_above_sma200": above200,
        "sma50_slope_10d_pct": _r(slope50),
        "golden_cross": bool(s50.iloc[-1] > s200.iloc[-1]) if pd.notna(s200.iloc[-1]) else None,
    }


def volume_confirmation(df: pd.DataFrame, n: int = 20) -> dict:
    """Compare recent volume with its average and check whether volume agrees with price."""
    vol, close = df["Volume"], df["Close"]
    avg = vol.rolling(n).mean().iloc[-1]
    ratio = vol.iloc[-1] / avg if avg else np.nan
    up = close.diff() > 0
    recent = df.iloc[-n:]
    up_vol = recent["Volume"][up.iloc[-n:]].mean()
    down_vol = recent["Volume"][~up.iloc[-n:]].mean()
    return {
        "last_vs_avg20": _r(ratio),
        "high_volume_today": bool(ratio >= 1.5) if pd.notna(ratio) else None,
        "up_day_vs_down_day_volume": _r(up_vol / down_vol) if down_vol else None,
        "volume_confirms_trend": bool(up_vol > down_vol) if pd.notna(up_vol) and pd.notna(down_vol) else None,
    }


def analyze(df: pd.DataFrame) -> dict:
    """Run the full rule engine on daily OHLCV and return a JSON-safe summary."""
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV frame missing columns: {missing}")
    df = df.dropna(subset=REQUIRED_COLS)
    if len(df) < MIN_BARS:
        return {"data_gaps": [f"only {len(df)} bars; need at least {MIN_BARS}"], "bars": len(df)}

    close = df["Close"]
    price = float(close.iloc[-1])
    a = atr(df)
    dmi = adx(df)
    m = macd(close)
    bb = bollinger(close)
    psar = parabolic_sar(df)
    pivots = find_pivots(df)
    swing = max(MIN_SWING_PCT, 2.5 * 100 * float(a.iloc[-1]) / price)
    swings = significant_pivots(pivots, swing)
    gaps = [] if len(df) >= 200 else [f"{len(df)} bars: 200-period averages unavailable"]

    indicators = {
        "price": _r(price),
        "rsi14": _r(rsi(close).iloc[-1]),
        "atr14": _r(a.iloc[-1]),
        "atr14_pct": _r(100 * a.iloc[-1] / price),
        "adx14": _r(dmi["adx"].iloc[-1]),
        "plus_di": _r(dmi["plus_di"].iloc[-1]),
        "minus_di": _r(dmi["minus_di"].iloc[-1]),
        "psar": _r(psar.iloc[-1]),
        "psar_position": "below_price" if psar.iloc[-1] < price else "above_price",
        "macd": _r(m["macd"].iloc[-1], 4),
        "macd_signal": _r(m["signal"].iloc[-1], 4),
        "macd_hist": _r(m["hist"].iloc[-1], 4),
        "macd_cross": ("bullish" if m["hist"].iloc[-1] > 0 >= m["hist"].iloc[-2]
                       else "bearish" if m["hist"].iloc[-1] < 0 <= m["hist"].iloc[-2] else "none"),
        "bb_upper": _r(bb["upper"].iloc[-1]),
        "bb_middle": _r(bb["middle"].iloc[-1]),
        "bb_lower": _r(bb["lower"].iloc[-1]),
        "bb_percent_b": _r((price - bb["lower"].iloc[-1]) / (bb["upper"].iloc[-1] - bb["lower"].iloc[-1])),
    }
    for n in (10, 20, 50, 200):
        indicators[f"sma{n}"] = _r(sma(close, n).iloc[-1])
        indicators[f"ema{n}"] = _r(ema(close, n).iloc[-1])

    return {
        "as_of": str(df.index[-1].date()),
        "bars": len(df),
        "indicators": indicators,
        "trend": trend_structure(df, indicators["adx14"]),
        "support_resistance": (levels := support_resistance(pivots, price, tol=max(float(a.iloc[-1]), price * 0.015))),
        "candlesticks": candlesticks.detect(df, levels, float(a.iloc[-1])),
        "volume": volume_confirmation(df),
        "patterns_found": detect_patterns(df, swings),
        "data_gaps": gaps,
    }
