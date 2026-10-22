"""Screener logic tests on hand-built frames (no network)."""
from datetime import datetime

import pandas as pd

from backend.app.data import screener

CFG = {"max_price_inr": 200, "min_avg_daily_volume": 100_000, "min_market_cap_cr": 300,
       "top_n": 2, "rank_weights": {"liquidity": 0.5, "fundamentals": 0.5}}


def test_prefilter_drops_surveillance_and_new_listings():
    """ASM/GSM symbols and stocks listed under a year are removed."""
    u = pd.DataFrame({"symbol": ["AAA", "BBB", "CCC"],
                      "name": ["A", "B", "C"],
                      "listed": pd.to_datetime(["2010-01-01", "2010-01-01", "2026-06-01"])})
    out = screener.prefilter(u, {"BBB"}, 1, today=datetime(2026, 10, 21))
    assert out["symbol"].tolist() == ["AAA"]


def test_apply_filters_thresholds():
    """Price, volume and market-cap limits are all enforced."""
    df = pd.DataFrame({"symbol": list("ABCD"), "price": [150, 250, 150, 150],
                       "avg_volume": [2e5, 2e5, 5e4, 2e5], "market_cap_cr": [500, 500, 500, 100]})
    assert screener.apply_filters(df, CFG)["symbol"].tolist() == ["A"]


def test_rank_prefers_liquid_quality_and_penalises_missing():
    """Higher liquidity and fundamentals rank first; missing data ranks last."""
    df = pd.DataFrame({
        "symbol": ["GOOD", "MID", "BLANK"],
        "avg_traded_value": [3e8, 2e8, 1e8],
        "returnOnEquity": [0.25, 0.10, None], "profitMargins": [0.15, 0.05, None],
        "revenueGrowth": [0.2, 0.05, None], "currentRatio": [2.0, 1.0, None],
        "debtToEquity": [20, 150, None],
    })
    out = screener.rank(df, CFG)
    assert out["symbol"].tolist() == ["GOOD", "MID"]
    assert out["rank"].tolist() == [1, 2]


def test_symbols_from_nested_json():
    """Surveillance symbols are found at any nesting depth."""
    payload = {"data": [{"symbol": "aaa"}, {"x": {"symbol": "BBB "}}]}
    assert screener._symbols_from_json(payload) == {"AAA", "BBB"}
