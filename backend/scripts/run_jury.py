"""Headless jury run (M3): run all six agents on tickers and print transcripts.

Usage: python backend/scripts/run_jury.py IDEA SUZLON YESBANK
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.orchestrator import run_jury, save_transcript  # noqa: E402

DISCLAIMER = "Analysis for education only. Not investment advice."


def show(t: dict) -> None:
    """Print a readable transcript: per agent status, score, citations and reasoning."""
    print(f"\n{'=' * 70}\n{t['symbol']}  ({t['seconds']}s)\n{'=' * 70}")
    for key, rec in t["agents"].items():
        print(f"\n--- {key.upper()} [{rec['status']}] {rec.get('provider', '')} {rec['seconds']}s")
        print("    KB:", "; ".join(f"{r['author']} {r['year']}" for r in rec["retrieved"]))
        if rec["status"] != "DONE":
            print("    ERROR:", rec["error"])
            continue
        o = rec["output"]
        score = o.get("score", o.get("risk_score"))
        label = "risk_score" if key == "devils_advocate" else "score"
        print(f"    {label}={score} confidence={o['confidence']}")
        print("    reasoning:", o["reasoning"][:700])
        if o.get("data_gaps"):
            print("    data_gaps:", o["data_gaps"])
        if rec.get("one_rule_redactions"):
            print("    ONE RULE redactions:", rec["one_rule_redactions"])
        if key == "devils_advocate":
            print("    where this analysis could be wrong:", o["where_analysis_could_be_wrong"][:500])
    print(f"\n{DISCLAIMER}")


def main(symbols: list[str]) -> None:
    """Run and save a transcript per symbol."""
    for sym in symbols or ["IDEA", "SUZLON", "YESBANK"]:
        t = run_jury(sym, on_event=lambda e: print(f"  {e['agent']}: {e['status']}"))
        show(t)
        print("saved:", save_transcript(t))


if __name__ == "__main__":
    main(sys.argv[1:])
