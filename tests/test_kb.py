"""Knowledge-base tests: chunking, frontmatter splitting, scoped retrieval."""
import pytest

from backend.app.kb import store
from backend.scripts import build_kb


def test_split_notes_on_frontmatter():
    """Multi-note markdown splits into one note per frontmatter block."""
    text = "---\ntitle: A\nauthor: X\nyear: 2000\n---\nBody A\n\n---\ntitle: B\n---\nBody B\n"
    notes = build_kb.split_notes(text)
    assert [m["title"] for m, _ in notes] == ["A", "B"]
    assert notes[0][1] == "Body A"


def test_every_agent_scope_is_known():
    """All scoped collections exist and devils_advocate sees all six."""
    for scope in store.AGENT_SCOPE.values():
        assert set(scope) <= set(store.COLLECTIONS)
    assert sorted(store.AGENT_SCOPE["devils_advocate"]) == sorted(store.COLLECTIONS)


@pytest.fixture(scope="module")
def built_kb(tmp_path_factory):
    """Build the KB into a temporary Chroma directory."""
    mp = pytest.MonkeyPatch()
    mp.setenv("JURY_KB_DIR", str(tmp_path_factory.mktemp("chroma")))
    build_kb.build()
    yield
    mp.undo()


def test_chunks_fit_minilm(built_kb):
    """Chunks stay within MiniLM's 256-token window."""
    tok = store.get_model().tokenizer
    docs = store.get_collection().get(include=["documents"])["documents"]
    assert docs
    assert max(len(tok.encode(d, add_special_tokens=False)) for d in docs) <= 256


def test_retrieval_respects_scope(built_kb):
    """Every hit for every agent comes from that agent's scope."""
    from backend.scripts.test_retrieval import run

    results = run(k=3)
    assert set(results) == set(store.AGENT_SCOPE)


def test_chunk_windows_overlap():
    """Long text splits into 240-token windows that overlap by 50 tokens."""
    tok = store.get_model().tokenizer
    words = ["stock", "market", "price", "value", "growth", "risk", "cash", "debt"]
    text = " ".join(words[i % len(words)] for i in range(400))  # one token per word
    chunks = store.chunk_text(text)
    lens = [len(tok.encode(c, add_special_tokens=False)) for c in chunks]
    assert len(chunks) > 1 and max(lens) <= store.CHUNK_TOKENS
    tail = tok.encode(chunks[0], add_special_tokens=False)[-store.CHUNK_OVERLAP:]
    head = tok.encode(chunks[1], add_special_tokens=False)[:store.CHUNK_OVERLAP]
    assert tail == head
