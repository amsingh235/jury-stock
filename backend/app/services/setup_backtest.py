"""Measured base rates for the nightly picks.

A deterministic setup score (0-100) is computed for every historical day from data available
on that day only. Days are pooled across the watchlist and bucketed into score bands; for each
band we measure how often the stock was up after HORIZON trading days (net of costs), plus the
typical gain and the typical worst dip along the way. Tonight's stock gets the hit rate of its
band as its base probability.

Caveats, shown with every number: overlapping 10-day windows make the effective sample smaller
than ``n``, and the watchlist is today's survivors, which flatters history (survivorship bias,
Brown et al., 1992).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ..data import market

HORIZON = 10          # trading days ahead
COST = 0.003          # round-trip costs counted against a "hit"
BAND = 10             # score band width
MIN_N = 150           # fewer samples than this falls back to the overall rate
OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "backtest"


def setup_score(df: pd.DataFrame) -> pd.Series:
    """Daily 0-100 setup score from trend, momentum, 52-week-high proximity, RSI, MACD and volume."""
    c, v = df["Close"], df["Volume"]
    sma20, sma50, sma200 = (c.rolling(n).mean() for n in (20, 50, 200))
    diff = c.diff()
    gain = diff.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-diff.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    mom = c.shift(21) / c.shift(252) - 1
    near_high = c / df["High"].rolling(252).max()
    up_vol = v.where(diff > 0).rolling(20, min_periods=5).mean()
    down_vol = v.where(diff < 0).rolling(20, min_periods=5).mean()

    parts = {
        "above_sma20": (c > sma20, 10),
        "above_sma50": (c > sma50, 15),
        "sma50_above_sma200": (sma50 > sma200, 15),
        "momentum_12_1_positive": (mom > 0, 15),
        "near_52w_high": (near_high > 0.85, 10),
        "rsi_healthy": ((rsi > 45) & (rsi < 70), 15),
        "macd_hist_positive": (hist > 0, 10),
        "volume_confirms": (up_vol > down_vol, 10),
    }
    score = sum(cond.astype(float) * w for cond, w in parts.values())
    return score.where(sma200.notna() & mom.notna())


def forward_stats(df: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    """Forward return and worst intra-window dip for each day (NaN where the future is unknown)."""
    c, low = df["Close"], df["Low"]
    fwd = c.shift(-horizon) / c - 1
    future_low = low[::-1].rolling(horizon, min_periods=horizon).min()[::-1].shift(-1)
    return pd.DataFrame({"fwd": fwd, "mae": future_low / c - 1})


def build_table(symbols: list[str], period: str = "3y", log=print) -> dict:
    """Pool all symbols' daily (score, outcome) pairs and summarise each score band."""
    rows = []
    for i, s in enumerate(symbols, 1):
        try:
            df = market.get_ohlcv(s, period=period)
        except market.MarketDataError as e:
            log(f"  skip {s}: {e}")
            continue
        frame = forward_stats(df).assign(score=setup_score(df)).dropna()
        rows.append(frame)
        if i % 10 == 0:
            log(f"  backtest data {i}/{len(symbols)}")
    data = pd.concat(rows, ignore_index=True)
    data["hit"] = data["fwd"] > COST
    data["band"] = (data["score"] // BAND * BAND).clip(upper=100 - BAND).astype(int)

    def summary(g: pd.DataFrame) -> dict:
        """Hit rate and return distribution for one group of days."""
        return {"n": int(len(g)), "hit_rate": round(float(g["hit"].mean()), 3),
                "median_fwd": round(float(g["fwd"].median()), 4), "p25_fwd": round(float(g["fwd"].quantile(0.25)), 4),
                "median_worst_dip": round(float(g["mae"].median()), 4)}

    table = {
        "built": date.today().isoformat(), "horizon_days": HORIZON, "cost": COST, "symbols": len(rows),
        "overall": summary(data),
        "bands": {str(b): summary(g) for b, g in data.groupby("band")},
        "caveats": ["overlapping windows: effective sample is far smaller than n",
                    "watchlist = today's survivors, so history looks better than it was"],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "setup_bands.json").write_text(json.dumps(table, indent=2), encoding="utf-8")
    return table


def load_table() -> dict | None:
    """The last built table, or None."""
    p = OUT_DIR / "setup_bands.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def base_rate(score: float, table: dict) -> dict:
    """Base probability for a setup score: its band's hit rate, or the overall rate if the band is thin."""
    band = str(int(min(score // BAND * BAND, 100 - BAND)))
    stats = table["bands"].get(band)
    if stats and stats["n"] >= MIN_N:
        return {"band": band, "source": "band", **stats}
    return {"band": band, "source": "overall (band too thin)", **table["overall"]}
