"""Nightly pipeline tests: DeepSeek bridge, trade plan, pick rules, guard levels, no-lookahead backtest."""
import numpy as np
import pandas as pd

from backend.app.agents import brief, guard
from backend.app.research import deepseek_bridge as ds
from backend.app.services import setup_backtest as sb
from backend.app.services import trade_plan

REPLY = """Sure, here is the research.
```json
{"stocks": [
  {"symbol": "IDEA", "news": [{"date": "2026-10-20", "headline": "Debt funding talks", "source": "MT Newswires"}],
   "bull_case": ["funding"], "bear_case": ["debt"]},
  {"symbol": "SUZLON.NS", "news": [{"headline": "Order win", "date": "2026-10-18"}]},
  {"symbol": 42, "news": "broken"}
]}
```
Hope this helps!"""


def test_parse_reply_tolerates_prose_and_bad_entries():
    """Fenced JSON inside prose parses; invalid stocks are dropped, valid ones kept."""
    r = ds.parse_reply(REPLY)
    assert set(r) == {"IDEA", "SUZLON"} and r["IDEA"]["news"][0]["source"] == "MT Newswires"
    tagged = ds.for_symbol(r, "IDEA.NS")
    assert "UNVERIFIED" in tagged["provenance"] and ds.for_symbol(r, "YESBANK") is None
    assert ds.parse_reply("") == {}


def test_prompt_lists_every_stock_and_forbids_opinions():
    """The prompt names each stock and asks for facts with sources, not buy/sell views."""
    ctx = {"symbol": "IDEA.NS", "info": {"longName": "Vodafone Idea"}, "chart": {"indicators": {"price": 11.6}}}
    p = ds.build_prompt([ctx])
    assert "IDEA | Vodafone Idea | 11.6" in p and "No price predictions" in p and "```json" in p


def test_trade_plan_uses_support_and_resistance():
    """Stop sits under nearby support, target at the next resistance, R:R computed."""
    chart = {"indicators": {"price": 100.0, "atr14": 2.0},
             "support_resistance": [{"type": "support", "level": 96.0}, {"type": "resistance", "level": 110.0}]}
    p = trade_plan.plan(chart)
    assert p["stop"] == 95.0 and p["target"] == 110.0 and p["reward_risk"] == 2.0


def _packet(score=70, base=0.48, rr_target=110.0, risk=40, liq=20):
    """A stock packet as the brief builds it."""
    chart = {"indicators": {"price": 100.0, "atr14": 2.0},
             "support_resistance": [{"type": "support", "level": 96.0}, {"type": "resistance", "level": rr_target}]}
    return {"symbol": "X.NS", "verdict": {"score": score}, "devils_advocate_risk": risk,
            "base_rate": {"hit_rate": base, "band": "60", "n": 900}, "plan": trade_plan.plan(chart),
            "avg_traded_value_cr": liq}


def test_rules_clamp_adjustment_and_require_everything():
    """Opus can move the base rate by at most 10 points, and every rule must pass."""
    cfg = brief.load_cfg()
    big = brief.apply_rules(_packet(), {"decision": "pick", "adjustment_pp": 40}, cfg)
    assert big["adjustment_pp"] == 10 and big["probability"] == 0.58 and big["is_pick"]
    assert not brief.apply_rules(_packet(), {"decision": "watch", "adjustment_pp": 10}, cfg)["is_pick"]
    assert not brief.apply_rules(_packet(rr_target=101.0), {"decision": "pick", "adjustment_pp": 10}, cfg)["is_pick"]
    assert not brief.apply_rules(_packet(base=0.40), {"decision": "pick", "adjustment_pp": 10}, cfg)["is_pick"]


def test_brief_guard_allows_picks_but_not_hype():
    """Strict mode removes advice phrasing; brief mode keeps it but removes certainty claims."""
    text = "Buy this stock. Guaranteed returns."
    assert "Buy this stock" not in guard.scrub_text(text)[0]
    clean, hits = guard.scrub_text(text, level="brief")
    assert "Buy this stock" in clean and hits == ["Guaranteed returns"]


def test_setup_score_has_no_lookahead():
    """Changing future prices never changes past scores."""
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
    df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": rng.integers(1e5, 1e6, 400)},
                      index=pd.bdate_range("2023-01-02", periods=400))
    a = sb.setup_score(df)
    df2 = df.copy()
    df2.iloc[350:, :4] *= 3
    b = sb.setup_score(df2)
    pd.testing.assert_series_equal(a.iloc[:350], b.iloc[:350])
    assert a.dropna().between(0, 100).all()
