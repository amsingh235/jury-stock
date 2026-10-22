"""Nightly JURY run with the manual DeepSeek step and the Opus brief.

Step 1 (evening, after market close):
  python backend/scripts/nightly.py prepare [--top 5] [SYMBOLS ...]
    -> writes data/deepseek/<date>_prompt.md. Paste it into chat.deepseek.com with Search and
       DeepThink ON, then paste DeepSeek's full reply into data/deepseek/<date>_reply.md.
Step 2:
  python backend/scripts/nightly.py run [--llm opus|free] [--top 5] [SYMBOLS ...]
    -> runs the six agents + Judge per stock, then the Opus brief:
       data/briefs/<date>.md (picks with probability, entry, stop, target) and data/ledger.csv.
Other:
  python backend/scripts/nightly.py backtest   # rebuild the setup base-rate table (weekly is plenty)
  python backend/scripts/nightly.py review     # score past picks in the ledger against what happened
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.agents.brief import LEDGER, run_brief  # noqa: E402
from backend.app.context import build_context  # noqa: E402
from backend.app.data import market  # noqa: E402
from backend.app.db import connect  # noqa: E402
from backend.app.llm.router import Router  # noqa: E402
from backend.app.orchestrator import run_jury, save_transcript  # noqa: E402
from backend.app.research import deepseek_bridge  # noqa: E402
from backend.app.services import setup_backtest  # noqa: E402


def pick_symbols(symbols: list[str], top: int) -> list[str]:
    """Explicit symbols, else the top-N of the screened watchlist."""
    if symbols:
        return symbols
    with connect() as conn:
        rows = [r["symbol"] for r in conn.execute("SELECT symbol FROM watchlist ORDER BY rank LIMIT ?", (top,))]
    if not rows:
        sys.exit("Watchlist is empty: run backend/scripts/screen.py first, or pass symbols.")
    return rows


def cmd_prepare(args) -> None:
    """Build data-only contexts and write the DeepSeek prompt."""
    syms = pick_symbols(args.symbols, args.top)
    ctxs = [build_context(s, log=lambda *a: None) for s in syms]
    prompt_path, reply_path = deepseek_bridge.save_prompt(deepseek_bridge.build_prompt(ctxs))
    print(f"\nDeepSeek prompt for {len(syms)} stocks: {prompt_path}\n")
    print("1. Open chat.deepseek.com, switch ON 'Search' and 'DeepThink'.")
    print(f"2. Paste the whole prompt file.\n3. Paste DeepSeek's whole reply into: {reply_path}")
    print("4. Run: python backend/scripts/nightly.py run" + (" " + " ".join(args.symbols) if args.symbols else ""))


def cmd_run(args) -> None:
    """Run the jury on each stock with the pasted research, then the Opus brief."""
    syms = pick_symbols(args.symbols, args.top)
    research = deepseek_bridge.load_reply(Path(args.reply) if args.reply else None)
    missing = [s for s in syms if s.upper().removesuffix(".NS") not in research]
    print(f"DeepSeek research loaded for {len(research)} stocks" + (f"; none for {', '.join(missing)}" if missing else ""))
    if setup_backtest.load_table() is None:
        print("Building the setup base-rate table first (one-off, a few minutes)...")
        setup_backtest.build_table(pick_symbols([], 50))
    router = Router.opus() if args.llm == "opus" else Router.from_config()
    transcripts = []
    for s in syms:
        print(f"\n== {s}")
        t = run_jury(s, router=router, research=research, debate_rounds=args.debate_rounds,
                     on_event=lambda e: print(f"  {e['agent']}: {e['status']}" + (f" (round {e['round']})" if "round" in e else "")))
        t["llm"] = args.llm
        save_transcript(t)
        v = t["verdict"]
        print(f"  verdict {v['score']}/100 {v['label']} ({v['confidence']['level']})")
        transcripts.append(t)
    brief = run_brief(transcripts, Router.opus())
    print(f"\nBrief: data/briefs/{brief['date']}.md · picks: {', '.join(brief['picks']) or 'none tonight'}")
    print(brief["disclaimer"])


def cmd_review(args) -> None:
    """Check each past pick: did price end its horizon above entry, and did it hit target or stop first?"""
    if not LEDGER.exists():
        sys.exit("No ledger yet.")
    rows = list(csv.DictReader(LEDGER.open(encoding="utf-8")))
    done, up, target_first = 0, 0, 0
    for r in rows:
        df = market.get_ohlcv(r["symbol"], period="6mo", use_cache=False)
        after = df[df.index > r["date"]].head(int(r["horizon_days"]))
        if len(after) < int(r["horizon_days"]):
            print(f"{r['date']} {r['symbol']}: open ({len(after)}/{r['horizon_days']} sessions)")
            continue
        done += 1
        final_up = after["Close"].iloc[-1] > float(r["entry"])
        hit_t = after.index[after["High"] >= float(r["target"])]
        hit_s = after.index[after["Low"] <= float(r["stop"])]
        first = "target" if len(hit_t) and (not len(hit_s) or hit_t[0] < hit_s[0]) else "stop" if len(hit_s) else "neither"
        up += final_up
        target_first += first == "target"
        print(f"{r['date']} {r['symbol']}: predicted {float(r['probability']):.0%} · ended {'UP' if final_up else 'DOWN'} · first hit: {first}")
    if done:
        print(f"\nClosed picks {done}: ended up {up / done:.0%}, target before stop {target_first / done:.0%}. "
              f"Compare with the average predicted probability to see if JURY is over-confident.")


def main(argv: list[str]) -> None:
    """Dispatch sub-commands."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("symbols", nargs="*")
        sp.add_argument("--top", type=int, default=5)
        if name == "run":
            sp.add_argument("--llm", choices=["opus", "free"], default="opus")
            sp.add_argument("--debate-rounds", type=int, default=2, help="Bull vs Bear rounds (0 = skip)")
            sp.add_argument("--reply", help="path to DeepSeek reply (default: today's file)")
    sub.add_parser("backtest")
    sub.add_parser("review")
    args = ap.parse_args(argv)
    if args.cmd == "prepare":
        cmd_prepare(args)
    elif args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "backtest":
        t = setup_backtest.build_table(pick_symbols([], 50))
        print(f"Base-rate table: overall hit rate {t['overall']['hit_rate']:.0%} over n={t['overall']['n']}")
    else:
        cmd_review(args)


if __name__ == "__main__":
    main(sys.argv[1:])
