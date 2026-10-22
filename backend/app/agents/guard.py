"""One Rule guard (spec §0, revised 2026-10-22): strip advice phrasing from agent and Judge text;
the nightly brief may name picks but never make hype or certainty claims."""
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
# Hype and certainty claims are banned everywhere, including the nightly brief.
HYPE = [p for p in BANNED if any(w in p for w in ("guaranteed", "sure", "will"))]
_RX = {"strict": [re.compile(p, re.I) for p in BANNED], "brief": [re.compile(p, re.I) for p in HYPE]}


def scrub_text(text: str, level: str = "strict") -> tuple[str, list[str]]:
    """Redact banned phrases from ``text``; return (clean text, phrases removed).

    ``strict`` (agents, Judge) removes all advice phrasing; ``brief`` (the owner-approved nightly
    picks) removes only hype and certainty claims.
    """
    hits = []
    for rx in _RX[level]:
        hits += [m.group(0) for m in rx.finditer(text)]
        text = rx.sub(REDACTION, text)
    return text, hits


def scrub(obj, level: str = "strict"):
    """Recursively scrub every string in a JSON-like object; return (clean object, hits)."""
    if isinstance(obj, str):
        return scrub_text(obj, level)
    if isinstance(obj, list):
        pairs = [scrub(v, level) for v in obj]
        return [p[0] for p in pairs], [h for p in pairs for h in p[1]]
    if isinstance(obj, dict):
        out, hits = {}, []
        for k, v in obj.items():
            out[k], h = scrub(v, level)
            hits += h
        return out, hits
    return obj, []
