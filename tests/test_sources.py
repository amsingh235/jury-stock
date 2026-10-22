"""Source manifest and fetch-script tests (no network)."""
import re

import yaml

from backend.scripts import build_kb, fetch_sources


def test_manifest_entries_are_wellformed_and_replace_real_notes():
    """Every entry names a known collection, an Author_Year_Title file, and an existing placeholder."""
    entries = yaml.safe_load(fetch_sources.MANIFEST.read_text(encoding="utf-8"))["sources"]
    for e in entries:
        assert (fetch_sources.RAW / e["collection"]).is_dir(), e
        assert build_kb.PDF_NAME.match(e["file"].rsplit(".", 1)[0]), e["file"]
        assert e["url"].startswith("https://") and e["verify"]
        if "replaces" in e:
            notes = (fetch_sources.RAW / e["collection"] / "placeholder_notes.md").read_text(encoding="utf-8")
            assert f"title: {e['replaces']}\n" in notes, e["replaces"]


def test_remove_placeholder_drops_only_that_note(tmp_path, monkeypatch):
    """Removing one note leaves its neighbours intact."""
    (tmp_path / "quant").mkdir()
    f = tmp_path / "quant" / "placeholder_notes.md"
    f.write_text("---\ntitle: A\nauthor: X\n---\nBody A\n\n---\ntitle: B\nauthor: Y\n---\nBody B\n", encoding="utf-8")
    monkeypatch.setattr(fetch_sources, "RAW", tmp_path)
    assert fetch_sources.remove_placeholder("quant", "A")
    left = f.read_text(encoding="utf-8")
    assert "Body A" not in left and "title: B" in left and "Body B" in left
    assert not fetch_sources.remove_placeholder("quant", "missing")


def test_verify_rejects_html_and_wrong_paper():
    """An HTML error page or a PDF without the expected words is rejected."""
    entry = {"file": "X_2000_Y.pdf", "verify": ["time series momentum"]}
    assert "not a PDF" in fetch_sources.verify(entry, b"<html>login</html>")
    txt = {"file": "X_1923_Y.txt", "verify": ["stock operator"]}
    assert fetch_sources.verify(txt, b"REMINISCENCES OF A STOCK OPERATOR") is None
    assert fetch_sources.verify(txt, b"something else") is not None


def test_real_txt_loads_as_primary_source(tmp_path):
    """Author_Year_Title.txt is indexed as a primary source with filename metadata."""
    p = tmp_path / "Lefevre_1923_Reminiscences_of_a_Stock_Operator.txt"
    p.write_text("Chapter I ...", encoding="utf-8")
    [(meta, body)] = build_kb.load_text_file(p, "contrarian")
    assert meta["author"] == "Lefevre" and meta["year"] == "1923" and meta["secondary_source"] is False
