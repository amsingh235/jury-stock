"""Smoke-test retrieval: one query per agent, assert scope, print top-3 titles."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.kb.retriever import retrieve  # noqa: E402
from backend.app.kb.store import AGENT_SCOPE  # noqa: E402

QUERIES = {
    "fundamentals": "is this business cheap relative to its earnings quality",
    "quant": "12-1 month momentum and short-term reversal",
    "chart": "head and shoulders failure rate and volume confirmation",
    "sentiment": "extreme retail attention and media pessimism",
    "news": "post earnings announcement drift after a surprise",
    "devils_advocate": "why the bullish consensus could be wrong",
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
