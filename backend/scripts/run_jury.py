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
    inp = t["inputs"]
    v = t["verdict"]
    lines = [
        f"# JURY verdict: {t['symbol']} ({inp['info'].get('longName', '')})",
        f"Run at {t['run_at']} · {t['seconds']}s · LLM: {t.get('llm', '?')}",
        "",
        f"## {v['score']} /100 · {v['label']}",
        f"Confidence: **{v['confidence']['level']}** ({v['confidence']['value']}: data completeness "
        f"{v['confidence']['completeness']} x agent agreement {v['confidence']['agreement']}; "
        f"Judge vs Chart Agent: {v['confidence']['chart_cross_check']})",
        "",
        "| Agent | Value | Weight |",
        "|---|---|---|",
        *[f"| {k} | {b['value']} | {b['weight']} |" for k, b in v["breakdown"].items()],
        "",
    ]
    if v.get("missing_agents"):
        lines += [f"Missing agents (weights re-normalised): {', '.join(v['missing_agents'])}", ""]
    if v["status"] == "DONE":
        e, cs = v["explainer"], v["explainer"]["chart_study"]
        lines += [
            "## The Judge's chart study",
            *( [f"![chart](../charts/{Path(v['chart_image']).name})", ""] if v.get("chart_image") else [] ),
            f"- **Trend:** {cs['trend_read']}",
            f"- **Candlesticks:** {cs['candlestick_read']}",
            f"- **Key levels:** {cs['key_levels']}",
            f"- **Volume:** {cs['volume_read']}",
            f"- **Chart bias:** {cs['chart_bias']} · agrees with Chart Agent: {cs['agrees_with_chart_agent']}",
            *( [f"- **Notes:** {cs['notes']}"] if cs.get("notes") else [] ),
            "",
            "## Strongest arguments for",
            *[f"{i}. {x}" for i, x in enumerate(e["pro_arguments"], 1)],
            "",
            "## Strongest arguments against",
            *[f"{i}. {x}" for i, x in enumerate(e["con_arguments"], 1)],
            "",
            f"## Decisive factors\n{e['decisive_factors']}",
            "",
            f"## Where this analysis could be wrong\n{e['where_analysis_could_be_wrong']}",
            "",
            f"## Confidence reasons\n{e['confidence_reasons']}",
            "",
            f"Judge audit: unsourced numbers {v['grounding']['unsourced_numbers'] or 'none'}; "
            f"unverified citations {v['grounding']['unverified_citations'] or 'none'}; "
            f"One Rule redactions {v['one_rule_redactions'] or 'none'}",
            "",
        ]
    else:
        lines += [f"Judge explainer failed: {v.get('error')}. The score above stands; narrative unavailable.", ""]
    lines += [
        "# Deliberation transcript",
        "",
        "## Inputs at a glance",
        f"- Price {inp['chart'].get('indicators', {}).get('price')} · trend {inp['chart'].get('trend', {}).get('direction')} "
        f"({inp['chart'].get('trend', {}).get('strength')}) · patterns: "
        + (", ".join(f"{p['name']} ({p['status']})" for p in inp['chart'].get('patterns_found', [])) or "none"),
        f"- Factors: {json.dumps({k: v for k, v in inp['factors'].items() if k != 'data_gaps'})}",
        f"- Piotroski F-score {inp['piotroski'].get('score')}/{inp['piotroski'].get('available')}",
        f"- Candlesticks (last 5 sessions): " + ("; ".join(f"{c['pattern']} {c['date']} after {c['prior_trend']} trend"
                                                          for c in inp['chart'].get('candlesticks', [])) or "none"),
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
    v = t["verdict"]
    print(f"\n{'=' * 70}\n{t['symbol']}  ({t['seconds']}s, LLM {t.get('llm')})\n"
          f"VERDICT {v['score']}/100 {v['label']}  confidence {v['confidence']['level']}\n{'=' * 70}")
    for key, rec in t["agents"].items():
        if rec["status"] != "DONE":
            print(f"  {key:16s} ERROR  {rec.get('error', '')[:120]}")
            continue
        o = rec["output"]
        val = o.get("score", o.get("risk_score"))
        flags = len(rec["grounding"]["unsourced_numbers"]) + len(rec["grounding"]["unverified_citations"])
        print(f"  {key:16s} {'risk' if key == 'devils_advocate' else 'score'}={val:<3} conf={o['confidence']:<6} "
              f"audit_flags={flags} {rec['seconds']}s")
    if v["status"] == "DONE":
        cs = v["explainer"]["chart_study"]
        print(f"  judge chart study: {cs['chart_bias']} (agrees with chart agent: {cs['agrees_with_chart_agent']})")
        print(f"    candlesticks: {cs['candlestick_read'][:300]}")
    else:
        print(f"  judge: {v.get('error')}")
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
