"""Scoped retrieval over the JURY knowledge base with source-aware reranking."""
from __future__ import annotations

from .store import embed, get_collection, scope_for

SECONDARY_PENALTY = 1.15
CONTRARIAN_BOOST = 0.9
OVERFETCH = 10
MAX_PER_SOURCE = 2  # long full texts must not crowd out the agent's other sources


def _score(meta: dict, distance: float, agent: str) -> float:
    """Adjust a cosine distance: penalise secondary sources, boost contrarian for devils_advocate."""
    score = distance
    if meta.get("secondary_source"):
        score *= SECONDARY_PENALTY
    if agent == "devils_advocate" and meta.get("collection") == "contrarian":
        score *= CONTRARIAN_BOOST
    return score


def retrieve(agent: str, query: str, k: int = 5) -> list[dict]:
    """Return the top-k chunks for ``query`` within ``agent``'s scope, reranked (lower score = better)."""
    scope = scope_for(agent)
    col = get_collection()
    if col.count() == 0:
        return []
    where = {"collection": scope[0]} if len(scope) == 1 else {"collection": {"$in": scope}}
    res = col.query(
        query_embeddings=embed([query]),
        n_results=min(k * OVERFETCH, col.count()),
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    hits = [
        {"id": i, "text": d, "metadata": m, "distance": dist, "score": _score(m, dist, agent)}
        for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]
    hits.sort(key=lambda h: h["score"])
    return diversify(hits, k)


def diversify(hits: list[dict], k: int, per_source: int = MAX_PER_SOURCE) -> list[dict]:
    """Keep the best-scoring hits while allowing at most ``per_source`` chunks from one document."""
    out, seen = [], {}
    for h in hits:
        key = (h["metadata"].get("author"), h["metadata"].get("year"), h["metadata"].get("title"))
        if seen.get(key, 0) < per_source:
            out.append(h)
            seen[key] = seen.get(key, 0) + 1
        if len(out) == k:
            break
    return out


def citation(meta: dict) -> str:
    """Format an (Author, Year) citation from chunk metadata."""
    return f"({meta.get('author', 'Unknown')}, {meta.get('year', 'n.d.')})"


def format_context(hits: list[dict]) -> str:
    """Render hits as numbered context blocks, each tagged with title and (Author, Year)."""
    blocks = []
    for n, h in enumerate(hits, 1):
        m = h["metadata"]
        flag = " [secondary]" if m.get("secondary_source") else ""
        blocks.append(f"[{n}] {m.get('title', 'Untitled')} {citation(m)}{flag}\n{h['text']}")
    return "\n\n".join(blocks)
