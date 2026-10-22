"""Run the jury for one stock: five analysts in parallel, the Bull vs Bear debate, the Devil's
Advocate, then the Judge.

Emits status events (THINKING / DONE / ERROR) through ``on_event`` so M5 can
stream them over SSE. LangGraph replaces the thread pool in M4 per spec §2.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .agents.debate import DEFAULT_ROUNDS, run_debate
from .agents.judge import run_judge
from .agents.runner import run_agent
from .context import build_context
from .llm.router import Router
from .services import chart_render

FIRST_WAVE = ["fundamentals", "quant", "chart", "sentiment", "news"]
TRANSCRIPT_DIR = Path(__file__).resolve().parents[2] / "data" / "transcripts"


def run_jury(symbol: str, router: Router | None = None, on_event=None, log=print,
             research: dict | None = None, debate_rounds: int = DEFAULT_ROUNDS) -> dict:
    """Build context, run all six agents and return the full transcript."""
    emit = on_event or (lambda e: None)
    router = router or Router.from_config()
    t0 = time.time()
    ctx = build_context(symbol, log=log, research=research)
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
    debate = run_debate(ctx, results, router, rounds=debate_rounds, on_event=emit) if debate_rounds else None
    ctx["debate"] = debate
    emit({"agent": "devils_advocate", "status": "THINKING"})
    da = run_agent("devils_advocate", ctx, router)
    results["devils_advocate"] = da
    emit({"agent": "devils_advocate", "status": da["status"], "record": da})
    emit({"agent": "judge", "status": "THINKING"})
    try:
        png = chart_render.render(ctx["ohlcv"], ctx["symbol"], ctx["chart"].get("support_resistance"))
    except Exception as e:  # the Judge can still study the chart engine output without the image
        log(f"chart render failed: {e}")
        png = None
    verdict = run_judge(ctx, results, router, png, debate)
    emit({"agent": "judge", "status": verdict["status"], "verdict": verdict})
    return {
        "symbol": ctx["symbol"],
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "seconds": round(time.time() - t0, 1),
        "inputs": {k: ctx[k] for k in ("info", "chart", "factors", "piotroski", "peers", "headlines", "events", "catalysts", "gaps", "deepseek")},
        "agents": results,
        "debate": debate,
        "verdict": verdict,
        "_ohlcv": ctx["ohlcv"],  # in-memory only (brief's setup score); never saved
    }


def save_transcript(t: dict) -> Path:
    """Write a transcript to data/transcripts/<SYMBOL>_<timestamp>.json."""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"{t['symbol']}_{t['run_at'].replace(':', '')}.json"
    saved = {k: v for k, v in t.items() if not k.startswith("_")}
    path.write_text(json.dumps(saved, indent=2, default=str), encoding="utf-8")
    return path
