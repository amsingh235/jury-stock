"""Deterministic levels for a pick: entry zone, stop, target, reward:risk."""
from __future__ import annotations


def plan(chart: dict, horizon_days: int = 10) -> dict:
    """Entry zone, stop (below nearest support or 2 ATR), target (nearest resistance or 2R) and R:R."""
    ind = chart.get("indicators", {})
    price, atr = ind.get("price"), ind.get("atr14")
    if not price or not atr:
        return {"error": "price/ATR unavailable"}
    levels = chart.get("support_resistance", [])
    supports = sorted((lv["level"] for lv in levels if lv["type"] == "support" and lv["level"] < price), reverse=True)
    resist = sorted(lv["level"] for lv in levels if lv["type"] == "resistance" and lv["level"] > price)
    stop, stop_basis = price - 2 * atr, "2 x ATR below price"
    if supports and price - supports[0] <= 3 * atr:
        stop, stop_basis = supports[0] - 0.5 * atr, f"0.5 ATR below support {supports[0]}"
    risk = price - stop
    target, target_basis = price + 2 * risk, "2R (no resistance close enough)"
    if resist:
        target, target_basis = resist[0], f"nearest resistance {resist[0]}"
    rr = (target - price) / risk if risk > 0 else 0.0
    return {
        "entry_zone": [round(price - 0.5 * atr, 2), round(price, 2)],
        "stop": round(stop, 2), "stop_basis": stop_basis,
        "target": round(target, 2), "target_basis": target_basis,
        "reward_risk": round(rr, 2), "risk_pct": round(100 * risk / price, 2),
        "horizon_days": horizon_days,
    }
