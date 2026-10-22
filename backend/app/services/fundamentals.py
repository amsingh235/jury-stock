"""Fundamentals inputs: key ratios, Piotroski F-score components and sector-peer comparison."""
from __future__ import annotations

import pandas as pd

RATIO_KEYS = ["trailingPE", "priceToBook", "enterpriseToEbitda", "returnOnEquity", "returnOnAssets",
              "profitMargins", "grossMargins", "operatingMargins", "revenueGrowth", "earningsGrowth",
              "debtToEquity", "currentRatio"]
LOWER_IS_BETTER = {"trailingPE", "priceToBook", "enterpriseToEbitda", "debtToEquity"}

ROWS = {
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "total_assets": ["Total Assets"],
    "cfo": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "lt_debt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "gross_profit": ["Gross Profit"],
    "revenue": ["Total Revenue", "Operating Revenue"],
    "shares": ["Ordinary Shares Number", "Share Issued"],
}


def _row(fin: dict[str, pd.DataFrame], name: str) -> pd.Series | None:
    """First matching statement row for ``name`` (newest year first), or None."""
    for frame in fin.values():
        if frame is None or frame.empty:
            continue
        for label in ROWS[name]:
            if label in frame.index:
                return frame.loc[label].dropna().sort_index(ascending=False)
    return None


def piotroski(fin: dict[str, pd.DataFrame]) -> dict:
    """Piotroski (2000) F-score components from the two latest annual statements.

    Components that can't be computed are None and listed in ``missing``; ``score``
    counts passed tests and ``available`` how many could be evaluated.
    """
    r = {k: _row(fin, k) for k in ROWS}

    def at(k: str, i: int):
        """Value of row ``k`` for year ``i`` (0 = latest) or None."""
        s = r[k]
        return float(s.iloc[i]) if s is not None and len(s) > i else None

    def ratio(a, b):
        """a / b when both exist and b is non-zero."""
        return a / b if a is not None and b not in (None, 0) else None

    roa0, roa1 = ratio(at("net_income", 0), at("total_assets", 0)), ratio(at("net_income", 1), at("total_assets", 1))
    lev0, lev1 = ratio(at("lt_debt", 0), at("total_assets", 0)), ratio(at("lt_debt", 1), at("total_assets", 1))
    cr0, cr1 = ratio(at("current_assets", 0), at("current_liabilities", 0)), ratio(at("current_assets", 1), at("current_liabilities", 1))
    gm0, gm1 = ratio(at("gross_profit", 0), at("revenue", 0)), ratio(at("gross_profit", 1), at("revenue", 1))
    at0, at1 = ratio(at("revenue", 0), at("total_assets", 0)), ratio(at("revenue", 1), at("total_assets", 1))
    cfo, ni = at("cfo", 0), at("net_income", 0)

    def cmp(a, b, higher=True):
        """a > b (or a < b) when both exist, else None."""
        return None if a is None or b is None else (a > b if higher else a < b)

    tests = {
        "roa_positive": None if roa0 is None else roa0 > 0,
        "cfo_positive": None if cfo is None else cfo > 0,
        "roa_improving": cmp(roa0, roa1),
        "accruals_cfo_above_net_income": cmp(cfo, ni),
        "leverage_falling": cmp(lev0, lev1, higher=False),
        "current_ratio_improving": cmp(cr0, cr1),
        "no_new_shares": None if at("shares", 0) is None or at("shares", 1) is None else at("shares", 0) <= at("shares", 1),
        "gross_margin_improving": cmp(gm0, gm1),
        "asset_turnover_improving": cmp(at0, at1),
    }
    return {
        "tests": tests,
        "score": sum(1 for v in tests.values() if v),
        "available": sum(1 for v in tests.values() if v is not None),
        "missing": [k for k, v in tests.items() if v is None],
    }


def revenue_trend(fin: dict[str, pd.DataFrame]) -> dict:
    """Annual revenue and net income, oldest to newest, in Rs. crore."""
    out = {}
    for k in ("revenue", "net_income"):
        s = _row(fin, k)
        out[k + "_cr"] = {} if s is None else {str(i.date()): round(float(v) / 1e7, 1) for i, v in s.sort_index().items()}
    return out


def peer_comparison(info: dict, peers: list[dict]) -> dict:
    """Sector-peer medians and this stock's percentile for each ratio (100 = best)."""
    same = [p for p in peers if p.get("sector") == info.get("sector") and p.get("symbol") != info.get("symbol")]
    out = {"sector": info.get("sector"), "peer_count": len(same), "ratios": {}}
    for k in RATIO_KEYS:
        mine = info.get(k)
        vals = [p[k] for p in same if p.get(k) is not None]
        if mine is None or len(vals) < 3:
            out["ratios"][k] = {"value": mine, "peer_median": None, "percentile": None}
            continue
        s = pd.Series(vals + [mine])
        pct = s.rank(pct=True, ascending=k not in LOWER_IS_BETTER).iloc[-1] * 100
        out["ratios"][k] = {"value": round(mine, 4), "peer_median": round(float(pd.Series(vals).median()), 4),
                            "percentile": round(float(pct))}
    return out
