"""Download the legal free full texts in config/sources_manifest.yaml into knowledge/raw.

Each file is verified (PDF signature + expected title words on its first pages) before
it is kept; then the placeholder note it replaces is removed from placeholder_notes.md.
Run build_kb.py afterwards. Usage: python backend/scripts/fetch_sources.py [--dry-run]
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "sources_manifest.yaml"
RAW = ROOT / "knowledge" / "raw"
HEADERS = {"User-Agent": "Mozilla/5.0 (JURY knowledge-base builder; research use)"}


def first_pages_text(data: bytes, pages: int = 2) -> str:
    """Lowercased text of a PDF's first pages (empty if unreadable)."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        return " ".join((p.extract_text() or "") for p in reader.pages[:pages]).lower()
    except Exception:
        return ""


def verify(entry: dict, data: bytes) -> str | None:
    """Return None if the download looks like the right document, else the reason it doesn't."""
    is_pdf = entry["file"].endswith(".pdf")
    if is_pdf and not data.startswith(b"%PDF"):
        return "not a PDF (likely an HTML login or error page)"
    text = first_pages_text(data) if is_pdf else data[:20000].decode("utf-8", "ignore").lower()
    text = re.sub(r"\s+", " ", text)
    missing = [w for w in entry.get("verify", []) if w.lower() not in text]
    return f"expected words not found: {missing}" if missing else None


def remove_placeholder(collection: str, title: str) -> bool:
    """Delete the note whose frontmatter title equals ``title`` from that collection's placeholder file."""
    path = RAW / collection / "placeholder_notes.md"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^(?=---\ntitle: )", text)
    keep = [b for b in blocks if not re.match(rf"---\ntitle: {re.escape(title)}\n", b)]
    if len(keep) == len(blocks):
        return False
    path.write_text("".join(keep), encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    """Fetch, verify, save and de-duplicate every manifest entry; print a summary."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="download and verify only; write nothing")
    args = ap.parse_args(argv)
    entries = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["sources"]
    ok, failed = 0, []
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60) as client:
        for e in entries:
            dest = RAW / e["collection"] / e["file"]
            if dest.exists():
                print(f"= {e['file']} (already present)")
                ok += 1
                continue
            try:
                r = client.get(e["url"])
                r.raise_for_status()
                problem = verify(e, r.content)
            except httpx.HTTPError as err:
                problem = f"{type(err).__name__}: {err}"
            if problem:
                failed.append((e["file"], e["url"], problem))
                print(f"x {e['file']}: {problem}")
                continue
            if not args.dry_run:
                dest.write_bytes(r.content)
                if e.get("replaces") and not remove_placeholder(e["collection"], e["replaces"]):
                    print(f"  ! placeholder '{e['replaces']}' not found in {e['collection']}")
            ok += 1
            print(f"+ {e['file']} ({len(r.content) // 1024} KB)")
    print(f"\n{ok}/{len(entries)} sources ready" + (" (dry run)" if args.dry_run else ""))
    for f, url, why in failed:
        print(f"  FAILED {f}\n         {url}\n         {why}")
    if ok and not args.dry_run:
        print("Next: python backend/scripts/build_kb.py")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
