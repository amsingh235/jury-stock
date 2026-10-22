"""Grounding auditor: deterministic post-check of every agent output.

Follows the "cite every number, mark it [UNSOURCED] otherwise" guardrail and the
Statement Auditor's consistency-check role from anthropics/financial-services
(Apache-2.0), done in code rather than with another LLM call so it costs nothing.

Two checks:
1. Every number quoted in the agent's prose must appear in its inputs or in the
   research it retrieved (allowing rounding and fraction<->percent conversion).
2. Every (Author, Year) citation must match a document it actually retrieved.
"""
from __future__ import annotations

import json
import re

NUM_RX = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?")
CITE_RX = re.compile(r"\(([A-Z][A-Za-z'\-]+)[^()]*?,\s*((?:19|20)\d{2})[a-z]?\)")
PROSE_SKIP = {"score", "risk_score", "scores", "factor_scores", "sentiment_score", "independent_sources", "citations"}


def _numbers_in(obj) -> list[float]:
    """Every numeric value in a JSON-like object, including numbers written inside strings."""
    out: list[float] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        for m in NUM_RX.finditer(obj):
            v = _parse(m.group(0))
            if v is not None:
                out.append(v)
        return out
    if isinstance(obj, dict):
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            out += _numbers_in(v)
    return out


def _parse(tok: str) -> float | None:
    """Parse '1,234.5' or '12%' to a float (percent sign dropped)."""
    try:
        return float(tok.rstrip("%").replace(",", ""))
    except ValueError:
        return None


def _prose(output: dict) -> list[str]:
    """All free-text strings in an output, skipping numeric score fields the agent sets itself."""
    texts: list[str] = []

    def walk(o, key=None):
        """Collect strings, ignoring skipped keys."""
        if key in PROSE_SKIP:
            return
        if isinstance(o, str):
            texts.append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)

    walk(output)
    return texts


def _trivial(v: float, tok: str) -> bool:
    """Small counts, years and window lengths that need no source (e.g. '3 sources', '2000', '12-1')."""
    return (abs(v) <= 12 and v == int(v) and "%" not in tok) or (1900 <= v <= 2100 and v == int(v)) \
        or v in (14, 20, 26, 50, 52, 100, 200)


def _matches(v: float, pool: list[float], rel: float = 0.015) -> bool:
    """True if ``v`` equals a pool value within rounding, directly or as fraction<->percent or crore scaling."""
    for p in pool:
        for cand in (p, p * 100, p / 100, p / 1e7):
            if cand == 0:
                if v == 0:
                    return True
                continue
            if abs(v - cand) <= max(rel * abs(cand), 0.011):
                return True
    return False


def _surname(author: str) -> str:
    """First author's surname, lowercased: 'Moskowitz, Ooi and Pedersen' -> 'moskowitz'."""
    m = re.match(r"[A-Za-z'\-]+", author.strip())
    return m.group(0).lower() if m else ""


def audit(output: dict, inputs: dict, retrieved: list[dict], research_text: str = "") -> dict:
    """Return unsourced numbers and unverified citations for one agent output."""
    pool = _numbers_in(inputs) + _numbers_in(research_text)
    unsourced, checked = [], 0
    for text in _prose(output):
        for m in NUM_RX.finditer(text):
            tok = m.group(0)
            v = _parse(tok)
            if v is None or _trivial(v, tok):
                continue
            checked += 1
            if not _matches(v, pool):
                unsourced.append(tok)

    known = {(_surname(r["author"]), str(r.get("year"))) for r in retrieved if r.get("author")}
    cited = set()
    for text in _prose(output):
        cited |= {(a.lower(), y) for a, y in CITE_RX.findall(text)}
    for c in output.get("citations", []):  # entries like "(Piotroski, 2000)" or "Piotroski, 2000"
        m = re.match(r"\(?\s*([A-Z][A-Za-z'\-]+)[^,]*,\s*((?:19|20)\d{2})", c)
        if m:
            cited.add((m.group(1).lower(), m.group(2)))
    unverified = sorted(f"({a.title()}, {y})" for a, y in cited if (a, y) not in known)
    return {
        "numbers_checked": checked,
        "unsourced_numbers": sorted(set(unsourced)),
        "citations_checked": len(cited),
        "unverified_citations": unverified,
        "grounded": not unsourced and not unverified,
    }


def mark_unsourced(output: dict, unsourced: list[str]) -> dict:
    """Append [UNSOURCED] after each unsourced number in the output's prose."""
    if not unsourced:
        return output
    rx = re.compile(r"(?<![\w.])(" + "|".join(re.escape(u) for u in sorted(unsourced, key=len, reverse=True)) + r")(?![\d])")

    def fix(o, key=None):
        """Recursively tag strings outside score fields."""
        if key in PROSE_SKIP:
            return o
        if isinstance(o, str):
            return rx.sub(r"\1 [UNSOURCED]", o)
        if isinstance(o, dict):
            return {k: fix(v, k) for k, v in o.items()}
        if isinstance(o, list):
            return [fix(v, key) for v in o]
        return o

    return fix(output)


def inputs_json(inputs: dict) -> str:
    """Stable JSON dump of inputs (used for the audit trail)."""
    return json.dumps(inputs, default=str, sort_keys=True)
