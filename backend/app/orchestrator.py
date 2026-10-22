"""Run the jury for one stock: five agents in parallel, then the Devil's Advocate.

Emits status events (THINKING / DONE / ERROR) through ``on_event`` so M5 can
stream them over SSE. LangGraph replaces the thread pool in M4 per spec §2.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .agents.runner import run_agent
from .context import build_context
from .llm.router import Router

FIRST_WAVE = ["fundamentals", "quant", "chart", "sentiment", "news"]
TRANSCRIPT_DIR = Path(__file__).resolve().parents[2] / "data" / "transcripts"


def run_jury(symbol: str, router: Router | None = None, on_event=None, log=print) -> dict:
    """Build context, run all six agents and return the full transcript."""
    emit = on_event or (lambda e: None)
    router = router or Router.from_config()
    t0 = time.time()
    ctx = build_context(symbol, log=log)
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(FIRST_WAVE)) as pool:
        futures = {}
        for key in FIRST_WAVE:
            emit({"agent": key, "status": "THINKING"})
            futures[pool.submit(run_agent, key, ctx, router)] = key
        for f in as_completed(futures):
            rec = f.result()
            results[rec["agent"]] = rec
            emit({"agent": rec["agent"], "status": rec["status"], "record": rec})
    ctx["agent_outputs"] = {k: r.get("output", {"status": r["status"], "error": r.get("error")})
                            for k, r in results.items()}
    emit({"agent": "devils_advocate", "status": "THINKING"})
    da = run_agent("devils_advocate", ctx, router)
    results["devils_advocate"] = da
    emit({"agent": "devils_advocate", "status": da["status"], "record": da})
    return {
        "symbol": ctx["symbol"],
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "seconds": round(time.time() - t0, 1),
        "inputs": {k: ctx[k] for k in ("info", "chart", "factors", "piotroski", "peers", "headlines", "events", "catalysts", "gaps")},
        "agents": results,
    }


def save_transcript(t: dict) -> Path:
    """Write a transcript to data/transcripts/<SYMBOL>_<timestamp>.json."""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"{t['symbol']}_{t['run_at'].replace(':', '')}.json"
    path.write_text(json.dumps(t, indent=2, default=str), encoding="utf-8")
    return path
