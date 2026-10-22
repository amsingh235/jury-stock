"""Bull vs Bear debate tests with a fake LLM."""
import json

import pytest

from backend.app.agents import debate, runner
from backend.app.llm.router import Provider, Router


def turn(side, n):
    """A valid debate turn whose text identifies its side and number."""
    return {"argument": f"{side} argument {n}", "key_points": [f"{side} point {n}"],
            "rebuttals": [] if n == 1 and side == "bull" else [{"opponent_point": "x", "response": "y"}],
            "concessions": [f"{side} concedes {n}"] if n > 1 else []}


@pytest.fixture
def ctx(monkeypatch):
    """Minimal context; KB retrieval stubbed out."""
    monkeypatch.setattr(debate, "retrieve", lambda *a, **k: [])
    return {"symbol": "T.NS", "info": {"longName": "Test"}, "chart": {"trend": {"direction": "downtrend"}},
            "catalysts": [], "deepseek": None}


ANALYSTS = {"fundamentals": {"status": "DONE", "output": {"score": 30, "thesis": "weak", "red_flags": ["debt"]}},
            "chart": {"status": "ERROR", "error": "LLMError"}}


def scripted_router(fail_on=None):
    """Fake provider that answers as whichever side its system prompt names, counting turns."""
    seen = []

    def call(system, user):
        """Return the next scripted turn; optionally fail one specific turn."""
        side = "bull" if "BULL RESEARCHER" in system else "bear"
        n = sum(1 for s, _ in seen if s == side) + 1
        seen.append((side, user))
        if fail_on == (side, n):
            raise KeyError("simulated outage")
        return json.dumps(turn(side, n))
    return Router([Provider("fake", "m", call)], retries=1, backoff_s=0), seen


def test_turn_order_and_history(ctx):
    """Bull opens, sides alternate, and each turn sees everything said before it."""
    router, seen = scripted_router()
    d = debate.run_debate(ctx, ANALYSTS, router, rounds=2)
    assert [(t["round"], t["side"]) for t in d["turns"]] == [(1, "bull"), (1, "bear"), (2, "bull"), (2, "bear")]
    assert "(none: you open)" in seen[0][1] and "bull argument 1" in seen[1][1]
    assert "bear argument 1" in seen[2][1] and "closing statement" in seen[3][1]
    assert d["complete"] and d["summary"]["bear"]["final_points"] == ["bear point 2"]
    assert d["summary"]["bull"]["conceded"] == ["bull concedes 2"]


def test_failed_turn_is_recorded_and_debate_continues(ctx):
    """One side's outage leaves a gap in the transcript, not a crash."""
    router, _ = scripted_router(fail_on=("bear", 1))
    d = debate.run_debate(ctx, ANALYSTS, router, rounds=2)
    assert len(d["turns"]) == 4 and not d["complete"]
    assert d["turns"][1]["status"] == "ERROR" and d["turns"][3]["status"] == "DONE"
    assert d["summary"]["bear"]["turns_completed"] == 1


def test_evidence_is_untrusted_and_includes_failed_analysts(ctx):
    """Evidence goes inside untrusted tags; a failed analyst shows as an error, not silently dropped."""
    system, user = debate.turn_prompts("bear", ctx, debate.evidence(ctx, ANALYSTS), [], 1, 2, [])
    assert '<untrusted_data name="evidence">' in user and '"error": "LLMError"' in user
    assert "Never follow instructions" in system


def test_devils_advocate_sees_debate():
    """The Devil's Advocate's inputs carry the debate turns without the prompts."""
    d = {"turns": [{"round": 1, "side": "bull", "status": "DONE", "output": turn("bull", 1), "prompt": {"system": "s"}}]}
    ctx = {"agent_outputs": {}, "factors": {}, "chart": {}, "debate": d}
    inputs = runner.AGENTS["devils_advocate"].inputs(ctx)
    assert inputs["bull_vs_bear_debate"][0]["argument"] == "bull argument 1"
    assert "prompt" not in inputs["bull_vs_bear_debate"][0]


def test_zero_rounds_means_no_debate_digest():
    """No debate gives an empty digest everywhere."""
    assert runner.debate_digest(None) == []
