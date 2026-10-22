"""Gather everything the agents need for one stock into a single context dict."""
from __future__ import annotations

from .data import market, news
from .research import deepseek_bridge
from .db import connect
from .services import chart_engine, factors, fundamentals

BENCHMARK = "^NSEI"


def watchlist_peers(limit: int = 60) -> list[dict]:
    """Cached ``info`` for watchlist stocks, used as the sector-peer pool."""
    with connect() as conn:
        syms = [r["symbol"] for r in conn.execute("SELECT symbol FROM watchlist ORDER BY rank LIMIT ?", (limit,))]
    peers = []
    for s in syms:
        try:
            peers.append(market.get_info(s))
        except market.MarketDataError:
            continue
    return peers


def build_context(symbol: str, log=print, research: dict | None = None) -> dict:
    """Fetch prices, fundamentals, chart, factors, headlines and events for ``symbol``.

    ``research`` is parsed DeepSeek output ({SYMBOL: research}); this stock's part is attached.
    """
    sym = market.to_nse(symbol)
    gaps: dict[str, list[str]] = {}
    log(f"[{sym}] prices")
    df = market.get_ohlcv(sym, period="2y")
    info = market.get_info(sym)
    try:
        bench = market.get_ohlcv(BENCHMARK, period="2y")
    except market.MarketDataError:
        bench = None
    log(f"[{sym}] financials")
    try:
        fin = market.get_financials(sym)
    except market.MarketDataError as e:
        fin, gaps["fundamentals"] = {}, [f"financial statements unavailable: {e}"]
    pio = fundamentals.piotroski(fin)
    if pio["missing"]:
        gaps.setdefault("fundamentals", []).append(f"F-score components unavailable: {', '.join(pio['missing'])}")
    peers = fundamentals.peer_comparison(info, watchlist_peers())
    if peers["peer_count"] < 3:
        gaps.setdefault("fundamentals", []).append(f"only {peers['peer_count']} sector peers in watchlist")
    log(f"[{sym}] news")
    headlines, failed = news.get_headlines(sym, info.get("longName"))
    gaps["news"] = [f"feed failed: {f}" for f in failed]
    events, gaps["events"] = news.get_event_candidates(sym, headlines)
    catalysts = news.get_catalysts(info, events)
    mcap = info.get("marketCap")
    return {
        "symbol": sym,
        "info": {k: v for k, v in info.items() if v is not None},
        "chart": chart_engine.analyze(df),
        "factors": factors.compute_factors(df, bench, mcap / 1e7 if mcap else None),
        "piotroski": pio,
        "financial_trend": fundamentals.revenue_trend(fin),
        "peers": peers,
        "headlines": headlines,
        "events": events,
        "catalysts": catalysts,
        "gaps": gaps,
        "deepseek": deepseek_bridge.for_symbol(research or {}, sym),
        "ohlcv": df,  # for chart rendering only; never passed to an agent prompt
    }
