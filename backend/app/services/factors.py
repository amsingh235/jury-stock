"""Quant factor engine (spec §4, Agent 2): precomputed factor inputs from OHLCV."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252
MONTH = 21


def _r(x, nd: int = 4):
    """Round to ``nd`` places, mapping NaN/None to None for JSON."""
    return None if x is None or pd.isna(x) else round(float(x), nd)


def compute_factors(df: pd.DataFrame, market: pd.DataFrame | None = None,
                    market_cap_cr: float | None = None) -> dict:
    """Momentum 12-1, 1-month reversal, 52w-high proximity, beta, idiosyncratic vol, size, liquidity.

    ``market`` is benchmark OHLCV (e.g. ^NSEI) for beta and idiosyncratic volatility.
    """
    close = df["Close"]
    ret = close.pct_change().dropna()
    gaps = []
    out: dict = {}

    if len(close) > TRADING_DAYS:
        out["momentum_12_1"] = _r(close.iloc[-MONTH] / close.iloc[-TRADING_DAYS] - 1)
    else:
        out["momentum_12_1"] = None
        gaps.append("under 12 months of history: momentum_12_1 unavailable")
    out["reversal_1m"] = _r(close.iloc[-1] / close.iloc[-MONTH] - 1) if len(close) > MONTH else None
    year = df.tail(TRADING_DAYS)
    out["high_52w_proximity"] = _r(close.iloc[-1] / year["High"].max())
    out["volatility_ann"] = _r(ret.tail(TRADING_DAYS).std() * np.sqrt(TRADING_DAYS))

    if market is not None and not market.empty:
        m = market["Close"].pct_change().dropna()
        joined = pd.concat([ret, m], axis=1, join="inner").tail(TRADING_DAYS).dropna()
        joined.columns = ["s", "m"]
        if len(joined) >= 60:
            beta = joined["s"].cov(joined["m"]) / joined["m"].var()
            resid = joined["s"] - beta * joined["m"]
            out["beta"] = _r(beta)
            out["idio_vol_ann"] = _r(resid.std() * np.sqrt(TRADING_DAYS))
        else:
            gaps.append("too little overlap with benchmark for beta")
    else:
        gaps.append("no benchmark data: beta and idiosyncratic volatility unavailable")
    out.setdefault("beta", None)
    out.setdefault("idio_vol_ann", None)

    out["market_cap_cr"] = _r(market_cap_cr, 1)
    if market_cap_cr is None:
        gaps.append("market cap unavailable: size factor unknown")
    tail = df.tail(60)
    out["avg_traded_value_cr"] = _r((tail["Close"] * tail["Volume"]).mean() / 1e7, 2)
    out["data_gaps"] = gaps
    return out
