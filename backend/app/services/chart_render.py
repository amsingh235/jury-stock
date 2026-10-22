"""Render a candlestick chart PNG for the Judge's visual chart study (spec §5.3 vision mode)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CHART_DIR = Path(__file__).resolve().parents[3] / "data" / "charts"


def render(df: pd.DataFrame, symbol: str, levels: list[dict] | None = None, bars: int = 120) -> Path:
    """Draw the last ``bars`` daily candles with SMA20/50/200, volume and S/R lines; return the PNG path."""
    import matplotlib

    matplotlib.use("Agg")  # headless
    import mplfinance as mpf

    full = df.copy()
    close = full["Close"]
    smas = {n: close.rolling(n).mean() for n in (20, 50, 200)}
    view = full.tail(bars)
    adds = [mpf.make_addplot(smas[n].tail(bars), width=1.0, color=c, label=f"SMA{n}")
            for n, c in ((20, "#1f77b4"), (50, "#ff7f0e"), (200, "#7f7f7f")) if smas[n].tail(bars).notna().any()]
    hlines = [lv["level"] for lv in (levels or [])]
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / f"{symbol.replace('^', '')}_{view.index[-1].date()}.png"
    kwargs = dict(type="candle", style="yahoo", volume=True, addplot=adds, figsize=(12, 7), tight_layout=True,
                  title=f"{symbol} daily, last {len(view)} sessions", savefig=dict(fname=str(path), dpi=110))
    if hlines:
        kwargs["hlines"] = dict(hlines=hlines, colors=["#2ca02c" if lv["type"] == "support" else "#d62728" for lv in levels],
                                linestyle="--", linewidths=0.8)
    mpf.plot(view, **kwargs)
    return path
