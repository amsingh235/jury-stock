"""Build the JURY knowledge base from knowledge/raw/<collection>/ (md, txt, pdf)."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.kb.store import RAW_DIR, chunk_text, embed, get_collection  # noqa: E402

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S | re.M)
# Author_Year_Title: metadata for .pdf files and real-source .txt files.
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


def strip_gutenberg(text: str) -> str:
    """Drop Project Gutenberg's licence header and footer, keeping only the book."""
    start = re.search(r"\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", text)
    end = re.search(r"\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG", text)
    return text[start.end() if start else 0: end.start() if end else len(text)].strip()


def load_text_file(path: Path, collection: str) -> list[tuple[dict, str]]:
    """Load an md/txt file.

    A .txt named Author_Year_Title.txt is a real full text (e.g. a public-domain book);
    anything else is placeholder notes, split on frontmatter and marked secondary.
    """
    m = PDF_NAME.match(path.stem)
    if path.suffix.lower() == ".txt" and m:
        meta = {"author": m["author"], "year": m["year"], "title": m["title"].replace("_", " "),
                "doc_type": "book", "secondary_source": False, "placeholder": False}
        return [(meta, strip_gutenberg(path.read_text(encoding="utf-8", errors="ignore")))]
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


COMMON_WORDS = set("the of and to in a is that for are with as by on this we be from at an not or which".split())
REF_RX = re.compile(r"\b(journal of|review of|econometrica|working paper|vol\.|pp\.)", re.I)


def is_prose(chunk: str) -> bool:
    """Keep readable prose; drop reference lists, numeric tables and garbled maths from full texts."""
    words = re.findall(r"[a-z]+", chunk.lower())
    if len(words) < 40:
        return False
    common = sum(w in COMMON_WORDS for w in words) / len(words)
    years = len(re.findall(r"\b(19|20)\d{2}\b", chunk))
    return common >= 0.12 and len(REF_RX.findall(chunk)) < 4 and years < 12


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
                if not meta.get("placeholder"):  # filter noise from full texts only
                    chunks = [c for c in chunks if is_prose(c)]
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
