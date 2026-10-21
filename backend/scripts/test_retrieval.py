"""Smoke-test retrieval: one query per agent, assert scope, print top-3 titles."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.kb.retriever import retrieve  # noqa: E402
from backend.app.kb.store import AGENT_SCOPE  # noqa: E402

QUERIES = {
    "value_analyst": "margin of safety and intrinsic value",
    "growth_analyst": "revenue growth and competitive moat",
    "technical_analyst": "moving averages and price momentum",
    "macro_analyst": "interest rates and the business cycle",
    "risk_manager": "position sizing and drawdown control",
    "contrarian": "buying when others are fearful",
    "devils_advocate": "why the bullish thesis could be wrong",
}


def run(k: int = 3) -> dict[str, list[dict]]:
    """Run each agent's query, check every hit is in scope, print top titles, return hits."""
    results = {}
    for agent, query in QUERIES.items():
        hits = retrieve(agent, query, k=k)
        assert hits, f"{agent}: no hits"
        for h in hits:
            assert h["metadata"]["collection"] in AGENT_SCOPE[agent], (agent, h["metadata"])
        print(f"\n{agent}: {query!r}")
        for h in hits:
            m = h["metadata"]
            print(f"  {h['score']:.3f}  [{m['collection']}] {m['title']} ({m['author']}, {m['year']})")
        results[agent] = hits
    return results


if __name__ == "__main__":
    run()
