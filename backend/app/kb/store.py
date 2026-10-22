"""Persistent Chroma vector store for the JURY knowledge base.

One collection ("jury_kb", cosine distance) holds every chunk. Each chunk carries a
``collection`` metadata field naming its source folder under knowledge/raw, and
AGENT_SCOPE maps each agent to the collections it is allowed to read.
"""
from __future__ import annotations

import os
import threading
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "knowledge" / "raw"
DEFAULT_DB_DIR = REPO_ROOT / "knowledge" / "chroma"

# Chroma client creation and model loading are not thread-safe; agents run in parallel.
_LOCK = threading.RLock()

COLLECTION_NAME = "jury_kb"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# MiniLM truncates input at 256 tokens, so chunks stay under that limit.
CHUNK_TOKENS = 240
CHUNK_OVERLAP = 50

COLLECTIONS = ["fundamentals", "quant", "chart", "sentiment", "news", "contrarian"]

# Each agent reads only its own collection; devils_advocate audits all six.
AGENT_SCOPE: dict[str, list[str]] = {
    "fundamentals": ["fundamentals"],
    "quant": ["quant"],
    "chart": ["chart"],
    "sentiment": ["sentiment"],
    "news": ["news"],
    "devils_advocate": list(COLLECTIONS),
}


def db_dir() -> Path:
    """Return the Chroma persistence directory (overridable via JURY_KB_DIR)."""
    return Path(os.environ.get("JURY_KB_DIR", DEFAULT_DB_DIR))


@lru_cache(maxsize=1)
def get_model():
    """Load the MiniLM sentence-transformer once and cache it for the process."""
    from sentence_transformers import SentenceTransformer

    with _LOCK:
        return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=4)
def _client(path: str):
    """Return a cached persistent Chroma client for ``path``."""
    import chromadb

    return chromadb.PersistentClient(path=path)


def get_collection():
    """Return (creating if needed) the cosine-distance ``jury_kb`` collection."""
    path = db_dir()
    path.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        return _client(str(path)).get_or_create_collection(
            COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with the cached MiniLM model (L2-normalised)."""
    model = get_model()
    with _LOCK:
        vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vecs.tolist()


def chunk_text(text: str, size: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping windows of ``size`` MiniLM tokens."""
    tok = get_model().tokenizer
    ids = tok.encode(text, add_special_tokens=False)
    if not ids:
        return []
    step = size - overlap
    chunks = []
    for start in range(0, len(ids), step):
        chunks.append(tok.decode(ids[start:start + size]).strip())
        if start + size >= len(ids):
            break
    return [c for c in chunks if c]


def scope_for(agent: str) -> list[str]:
    """Return the collections ``agent`` may read; raise KeyError for unknown agents."""
    if agent not in AGENT_SCOPE:
        raise KeyError(f"Unknown agent {agent!r}; expected one of {sorted(AGENT_SCOPE)}")
    return AGENT_SCOPE[agent]
