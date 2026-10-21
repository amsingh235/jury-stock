"""Build the JURY knowledge base from knowledge/raw/<collection>/ (md, txt, pdf)."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.kb.store import RAW_DIR, chunk_text, embed, get_collection  # noqa: E402

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S | re.M)
PDF_NAME = re.compile(r"^(?P<author>[^_]+)_(?P<year>\d{4})_(?P<title>.+)$")


def parse_frontmatter(block: str) -> dict:
    """Parse a simple ``key: value`` frontmatter block into a dict."""
    meta = {}
    for line in block.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip().strip("\"'")
    return meta


def split_notes(text: str) -> list[tuple[dict, str]]:
    """Split a multi-note markdown file into (frontmatter, body) pairs."""
    matches = list(FRONTMATTER.finditer(text))
    if not matches:
        return [({}, text)]
    notes = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        notes.append((parse_frontmatter(m.group(1)), text[m.end():end].strip()))
    return notes


def load_text_file(path: Path, collection: str) -> list[tuple[dict, str]]:
    """Load an md/txt file; every note is a placeholder secondary source."""
    docs = []
    for meta, body in split_notes(path.read_text(encoding="utf-8")):
        meta.setdefault("title", path.stem)
        meta.update(secondary_source=True, placeholder=True)
        docs.append((meta, body))
    return docs


def load_pdf(path: Path, collection: str) -> list[tuple[dict, str]]:
    """Load a PDF; metadata comes from the Author_Year_Title.pdf filename."""
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    m = PDF_NAME.match(path.stem)
    meta = (
        {"author": m["author"], "year": m["year"], "title": m["title"].replace("_", " ")}
        if m else {"title": path.stem}
    )
    meta.update(doc_type="book", secondary_source=False, placeholder=False)
    return [(meta, text)]


LOADERS = {".md": load_text_file, ".txt": load_text_file, ".pdf": load_pdf}


def clean_meta(meta: dict, collection: str, source: Path, idx: int) -> dict:
    """Coerce metadata to Chroma-safe scalar values and add provenance fields."""
    out = {k: v if isinstance(v, (str, int, float, bool)) else str(v) for k, v in meta.items()}
    out.update(collection=collection, agent=collection, source=source.name, chunk=idx)
    out.setdefault("author", "Unknown")
    out["year"] = str(out.get("year", "n.d."))
    return out


def build(raw_dir: Path = RAW_DIR, reset: bool = True) -> int:
    """Chunk, embed and upsert every document under ``raw_dir``; return chunk count."""
    col = get_collection()
    if reset and col.count():
        col.delete(ids=col.get(include=[])["ids"])
    total = 0
    for coll_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        for path in sorted(coll_dir.iterdir()):
            loader = LOADERS.get(path.suffix.lower())
            if not loader:
                continue
            for meta, body in loader(path, coll_dir.name):
                chunks = chunk_text(body)
                if not chunks:
                    continue
                ids, metas = [], []
                for i, _ in enumerate(chunks):
                    key = f"{coll_dir.name}/{path.name}/{meta.get('title')}/{i}"
                    ids.append(hashlib.sha1(key.encode()).hexdigest())
                    metas.append(clean_meta(meta, coll_dir.name, path, i))
                col.upsert(ids=ids, documents=chunks, metadatas=metas, embeddings=embed(chunks))
                total += len(chunks)
                print(f"[{coll_dir.name}] {meta.get('title')}: {len(chunks)} chunks (total {total})")
    print(f"Done: {total} chunks in collection, {col.count()} stored.")
    return total


if __name__ == "__main__":
    build()
