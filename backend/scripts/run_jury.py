"""Headless jury run (M3): run all six agents on tickers, print and save everything.

Usage:
  python backend/scripts/run_jury.py IDEA SUZLON YESBANK          # free tier (Groq -> Gemini)
  python backend/scripts/run_jury.py IDEA --llm opus               # Opus on your Claude subscription

Each run saves the raw JSON transcript and a full Markdown report to data/transcripts/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.llm.router import Router  # noqa: E402
from backend.app.orchestrator import run_jury, save_transcript  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = yaml.safe_load((ROOT / "config" / "judge_weights.yaml").read_text(encoding="utf-8"))
DISCLAIMER = WEIGHTS["disclaimer"]


def preliminary_score(t: dict) -> tuple[float | None, str, list[str]]:
    """Spec §6 formula on whatever agents finished (re-weighted); the real Judge arrives in M4."""
    w = WEIGHTS["weights"]
    total, used, missing = 0.0, 0.0, []
    for key, weight in w.items():
        rec = t["agents"].get(key, {})
        if rec.get("status") != "DONE":
            missing.append(key)
            continue
        o = rec["output"]
        val = 100 - o["risk_score"] if key == "devils_advocate" else o["score"]
        total += weight * val
        used += weight
    if not used:
        return None, "n/a", missing
    score = round(total / used, 1)
    label = next(lv["label"] for lv in WEIGHTS["labels"] if score >= lv["min"])
    return score, label, missing


def _md_value(v, indent: int = 0) -> str:
    """Render a JSON value as Markdown bullets."""
    pad = "  " * indent
    if isinstance(v, dict):
        return "\n".join(f"{pad}- **{k}**: {_md_value(x, indent + 1).lstrip() if not isinstance(x, (dict, list)) else chr(10) + _md_value(x, indent + 1)}"
                         for k, x in v.items())
    if isinstance(v, list):
        if not v:
            return f"{pad}- (none)"
        return "\n".join(_md_value(x, indent) if isinstance(x, (dict, list)) else f"{pad}- {x}" for x in v)
    return f"{pad}{v}"


def report_markdown(t: dict) -> str:
    """Everything from one run as a readable Markdown report."""
    score, label, missing = preliminary_score(t)
    inp = t["inputs"]
    lines = [
        f"# JURY run: {t['symbol']} ({inp['info'].get('longName', '')})",
        f"Run at {t['run_at']} · {t['seconds']}s · LLM: {t.get('llm', '?')}",
        "",
        f"## Preliminary score: {score} /100 · {label}",
        "Spec §6 formula over the agents that finished; the deterministic Judge and its explanation come in M4."
        + (f" Missing agents (weights re-normalised): {', '.join(missing)}." if missing else ""),
        "",
        "## Inputs at a glance",
        f"- Price {inp['chart'].get('indicators', {}).get('price')} · trend {inp['chart'].get('trend', {}).get('direction')} "
        f"({inp['chart'].get('trend', {}).get('strength')}) · patterns: "
        + (", ".join(f"{p['name']} ({p['status']})" for p in inp['chart'].get('patterns_found', [])) or "none"),
        f"- Factors: {json.dumps({k: v for k, v in inp['factors'].items() if k != 'data_gaps'})}",
        f"- Piotroski F-score {inp['piotroski'].get('score')}/{inp['piotroski'].get('available')}",
        f"- Headlines: {len(inp['headlines'])} · events: {len(inp['events'])} · catalysts: "
        + ("; ".join(f"{c['catalyst']} {c['date']} (in {c['days_until']}d)" for c in inp.get('catalysts', [])) or "none"),
        f"- Data gaps: {json.dumps(inp['gaps'])}",
        "",
    ]
    for key, rec in t["agents"].items():
        lines += [f"## {key.replace('_', ' ').title()} — {rec['status']} ({rec.get('provider', '-')}, {rec['seconds']}s)", ""]
        lines.append("**Research retrieved:** " + "; ".join(
            f"{r['author']} ({r['year']}){' [secondary]' if r['secondary'] else ''}" for r in rec["retrieved"]))
        if rec["status"] != "DONE":
            lines += ["", f"**Error:** {rec.get('error')}", ""]
            continue
        g = rec["grounding"]
        lines += [
            f"**Grounding audit:** {g['numbers_checked']} numbers checked, unsourced: {g['unsourced_numbers'] or 'none'}; "
            f"{g['citations_checked']} citations checked, unverified: {g['unverified_citations'] or 'none'}",
            f"**One Rule redactions:** {rec['one_rule_redactions'] or 'none'}",
            "",
            _md_value(rec["output"]),
            "",
        ]
    lines += ["---", f"*{DISCLAIMER}*", ""]
    return "\n".join(lines)


def show(t: dict) -> None:
    """Print a short console summary of a run."""
    score, label, missing = preliminary_score(t)
    print(f"\n{'=' * 70}\n{t['symbol']}  ({t['seconds']}s, LLM {t.get('llm')})  preliminary {score}/100 {label}\n{'=' * 70}")
    for key, rec in t["agents"].items():
        if rec["status"] != "DONE":
            print(f"  {key:16s} ERROR  {rec.get('error', '')[:120]}")
            continue
        o = rec["output"]
        val = o.get("score", o.get("risk_score"))
        flags = len(rec["grounding"]["unsourced_numbers"]) + len(rec["grounding"]["unverified_citations"])
        print(f"  {key:16s} {'risk' if key == 'devils_advocate' else 'score'}={val:<3} conf={o['confidence']:<6} "
              f"audit_flags={flags} {rec['seconds']}s")
    print(f"\n{DISCLAIMER}")


def main(argv: list[str]) -> None:
    """Parse arguments, run each symbol, save transcript + report."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbols", nargs="*", default=["IDEA", "SUZLON", "YESBANK"])
    ap.add_argument("--llm", choices=["free", "opus"], default="free",
                    help="free = Groq/Gemini (API keys); opus = Opus via your Claude subscription (claude CLI)")
    args = ap.parse_args(argv)
    router = Router.opus() if args.llm == "opus" else Router.from_config()
    for sym in args.symbols:
        t = run_jury(sym, router=router, on_event=lambda e: print(f"  {e['agent']}: {e['status']}"))
        t["llm"] = args.llm
        show(t)
        path = save_transcript(t)
        report = path.with_suffix(".md")
        report.write_text(report_markdown(t), encoding="utf-8")
        print(f"transcript: {path}\nreport:     {report}")


if __name__ == "__main__":
    main(sys.argv[1:])
