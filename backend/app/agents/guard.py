"""One Rule guard (spec §0): strip advice phrasing from any agent or judge text."""
from __future__ import annotations

import re

REDACTION = "[removed: advice phrasing]"

BANNED = [
    r"\b(strong\s+)?(buy|sell|accumulate|short)\s+(this|the|these)\s+(stock|share|scrip)s?\b",
    r"\b(strong|must|good)\s+(buy|sell)\b",
    r"\bguaranteed?\s+(return|profit|gain)s?\b",
    r"\bsure\s+(profit|shot|gain)s?\b",
    r"\bwill\s+(go\s+up|rise|rally|double|triple|fall|crash)\b[^.]{0,30}?\d+\s?%",
    r"\b(price\s+)?target\s+(price\s+)?(of\s+)?(rs\.?|₹|inr)\s?\d",
    r"\binvest(ors)?\s+should\s+(buy|sell)\b",
    r"\b(we|i)\s+recommend\s+(buying|selling)\b",
]
_RX = [re.compile(p, re.I) for p in BANNED]


def scrub_text(text: str) -> tuple[str, list[str]]:
    """Redact banned phrases from ``text``; return (clean text, phrases removed)."""
    hits = []
    for rx in _RX:
        hits += [m.group(0) for m in rx.finditer(text)]
        text = rx.sub(REDACTION, text)
    return text, hits


def scrub(obj):
    """Recursively scrub every string in a JSON-like object; return (clean object, hits)."""
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, list):
        pairs = [scrub(v) for v in obj]
        return [p[0] for p in pairs], [h for p in pairs for h in p[1]]
    if isinstance(obj, dict):
        out, hits = {}, []
        for k, v in obj.items():
            out[k], h = scrub(v)
            hits += h
        return out, hits
    return obj, []
