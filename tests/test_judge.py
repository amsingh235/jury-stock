"""Judge tests: deterministic score fusion, confidence, chart cross-check, explainer flow (fake LLM)."""
import json

import pandas as pd
import pytest

from backend.app.agents import judge
from backend.app.llm.router import Provider, Router

CFG = {"weights": {"fundamentals": 0.2, "quant": 0.15, "chart": 0.2, "sentiment": 0.15, "news": 0.1,
                   "devils_advocate": 0.2},
       "labels": [{"min": 70, "label": "STRONG POSITIVE SIGNALS"}, {"min": 45, "label": "MIXED"},
                  {"min": 0, "label": "WEAK SIGNALS"}],
       "disclaimer": "Analysis for education only. Not investment advice."}


def rec(score=None, risk=None, conf="HIGH", grounded=True):
    """A finished agent record."""
    out = {"confidence": conf}
    out.update({"risk_score": risk} if risk is not None else {"score": score})
    return {"status": "DONE", "output": out, "grounding": {"grounded": grounded}}


def all_agents(v=80, risk=20):
    """Six agreeing agents."""
    a = {k: rec(v) for k in ["fundamentals", "quant", "chart", "sentiment", "news"]}
    a["devils_advocate"] = rec(risk=risk)
    return a


def test_formula_matches_spec():
    """0.20F + 0.15Q + 0.20C + 0.15S + 0.10N + 0.20(100-D)."""
    a = {"fundamentals": rec(60), "quant": rec(40), "chart": rec(30), "sentiment": rec(50), "news": rec(70),
         "devils_advocate": rec(risk=70)}
    f = judge.compute_score(a, CFG)
    assert f["score"] == pytest.approx(0.2 * 60 + 0.15 * 40 + 0.2 * 30 + 0.15 * 50 + 0.1 * 70 + 0.2 * 30)
    assert f["label"] == "WEAK SIGNALS"


def test_labels_and_missing_agent_renormalises():
    """Agreeing high scores give the top label; a failed agent is left out, not counted as zero."""
    assert judge.compute_score(all_agents(), CFG)["label"] == "STRONG POSITIVE SIGNALS"
    a = all_agents()
    a["news"] = {"status": "ERROR"}
    f = judge.compute_score(a, CFG)
    assert f["score"] == 80 and f["missing"] == ["news"] and f["completeness"] < 1


def test_confidence_drops_on_disagreement_and_chart_conflict():
    """Spread-out agents and a Judge/Chart conflict both lower confidence."""
    agree = judge.compute_score(all_agents(), CFG)
    split = all_agents()
    split["chart"], split["quant"] = rec(10), rec(95)
    spread = judge.compute_score(split, CFG)
    assert spread["agreement"] < agree["agreement"]
    base = judge.confidence(agree, "favourable", "favourable")
    clash = judge.confidence(agree, "unfavourable", "favourable")
    assert clash["value"] < base["value"] and clash["chart_cross_check"] == "disagree"


def test_run_judge_with_fake_llm_keeps_deterministic_score(monkeypatch, tmp_path):
    """The explainer cannot move the score; its chart study and narrative are attached."""
    reply = {"chart_study": {"trend_read": "Lower highs since August.", "candlestick_read": "Doji near resistance.",
                             "key_levels": "Support below.", "volume_read": "Rising on down days.",
                             "chart_bias": "unfavourable", "agrees_with_chart_agent": False},
             "pro_arguments": ["a"], "con_arguments": ["b"], "decisive_factors": "c",
             "where_analysis_could_be_wrong": "d", "confidence_reasons": "e", "score": 99}
    seen = {}

    def fake(system, user, image=None):
        """Capture the prompt and image, return a canned reply."""
        seen.update(system=system, image=image)
        return json.dumps(reply)

    monkeypatch.setattr(judge, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(judge, "load_config", lambda: CFG)
    png = tmp_path / "c.png"
    png.write_bytes(b"x")
    ctx = {"symbol": "T.NS", "info": {}, "chart": {"candlesticks": [], "patterns_found": []}}
    v = judge.run_judge(ctx, all_agents(), Router([Provider("fake", "m", fake)], backoff_s=0), png)
    assert v["status"] == "DONE" and v["score"] == 80 and v["label"] == "STRONG POSITIVE SIGNALS"
    assert seen["image"] == png and "CHART STUDY DUTY" in seen["system"]
    assert v["confidence"]["chart_cross_check"] == "disagree"
    assert v["disclaimer"] == CFG["disclaimer"]
