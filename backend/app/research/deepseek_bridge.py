"""Manual DeepSeek research bridge (free, no API).

JURY writes one prompt for the stocks being analysed; the user pastes it into DeepSeek's
chat (with Search and DeepThink on), saves the reply to a file, and JURY parses it. The
reply is treated as UNVERIFIED secondary research: chatbots can invent headlines, so the
agents see it inside <untrusted_data> tags, labelled with its provenance.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from ..llm.router import extract_json

ROOT = Path(__file__).resolve().parents[3]
DS_DIR = ROOT / "data" / "deepseek"


class NewsItem(BaseModel):
    """One dated news item DeepSeek found."""

    date: str | None = None
    headline: str
    source: str | None = None
    url: str | None = None


class StockResearch(BaseModel):
    """DeepSeek's research for one stock."""

    symbol: str
    news: list[NewsItem] = Field(default_factory=list)
    upcoming_events: list[str] = Field(default_factory=list)
    promoter_and_governance: str = ""
    sector_context: str = ""
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class ResearchReply(BaseModel):
    """The whole reply."""

    stocks: list[StockResearch]


PROMPT_TEMPLATE = """You are a careful equity research assistant. Use web search. Research each NSE-listed stock below
as of {today}, covering the last 30 days plus anything scheduled in the next 30 days.

For EACH stock find:
1. Dated news headlines with the source name and URL (company announcements, results, orders, regulatory
   actions, rating changes, block/bulk deals). Prefer NSE/BSE filings and established outlets.
2. Upcoming events with dates (results date, AGM, record dates, policy decisions affecting the sector).
3. Promoter and governance: promoter buying/selling, pledged shares, auditor changes, SEBI actions.
4. Sector context in one or two sentences.
5. The 2-3 strongest bull points and the 2-3 strongest bear points, each tied to a fact above.
6. Key risks.

RULES:
- Only report things you actually found. If you find nothing for a field, leave it empty. Never guess.
- Give a date and source for every news item. No source means leave it out.
- No price predictions and no buy/sell opinions: facts and arguments only.

Reply with ONE JSON block in exactly this shape and nothing else:
```json
{schema_example}
```

STOCKS (symbol, company, last close in Rs., what our data already shows):
{stock_lines}
"""

SCHEMA_EXAMPLE = {
    "stocks": [{
        "symbol": "IDEA",
        "news": [{"date": "2026-10-20", "headline": "...", "source": "NSE filing", "url": "https://..."}],
        "upcoming_events": ["2026-11-13: Q2 results"],
        "promoter_and_governance": "...",
        "sector_context": "...",
        "bull_case": ["..."],
        "bear_case": ["..."],
        "key_risks": ["..."],
        "sources": ["https://..."],
    }]
}


def stock_line(ctx: dict) -> str:
    """One compact line per stock telling DeepSeek what JURY already knows."""
    ch, info = ctx.get("chart", {}), ctx.get("info", {})
    trend = ch.get("trend", {}).get("direction", "?")
    rsi = ch.get("indicators", {}).get("rsi14")
    return (f"- {ctx['symbol'].removesuffix('.NS')} | {info.get('longName', '?')} | "
            f"{ch.get('indicators', {}).get('price', '?')} | trend {trend}, RSI {rsi}, sector {info.get('sector', '?')}")


def build_prompt(contexts: list[dict], today: date | None = None) -> str:
    """The single prompt to paste into DeepSeek for all ``contexts``."""
    return PROMPT_TEMPLATE.format(
        today=(today or date.today()).isoformat(),
        schema_example=json.dumps(SCHEMA_EXAMPLE, indent=1),
        stock_lines="\n".join(stock_line(c) for c in contexts),
    )


def save_prompt(prompt: str, today: date | None = None) -> tuple[Path, Path]:
    """Write today's prompt and an empty reply file; return (prompt_path, reply_path)."""
    d = (today or date.today()).isoformat()
    DS_DIR.mkdir(parents=True, exist_ok=True)
    p, r = DS_DIR / f"{d}_prompt.md", DS_DIR / f"{d}_reply.md"
    p.write_text(prompt, encoding="utf-8")
    if not r.exists():
        r.write_text("", encoding="utf-8")
    return p, r


def parse_reply(text: str) -> dict[str, dict]:
    """Parse DeepSeek's reply into {SYMBOL: research}; tolerant of prose, fences and partial fields."""
    if not text.strip():
        return {}
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = extract_json(fence.group(1) if fence else text)
    try:
        reply = ResearchReply.model_validate(raw)
    except ValidationError:
        # Keep whichever stocks validate rather than losing the whole reply.
        stocks = []
        for s in raw.get("stocks", []) if isinstance(raw, dict) else []:
            try:
                stocks.append(StockResearch.model_validate(s))
            except ValidationError:
                continue
        reply = ResearchReply(stocks=stocks)
    return {s.symbol.upper().removesuffix(".NS"): s.model_dump() for s in reply.stocks}


def load_reply(path: Path | None = None) -> dict[str, dict]:
    """Research from ``path``, or today's reply file if it exists and is filled in."""
    path = path or DS_DIR / f"{date.today().isoformat()}_reply.md"
    return parse_reply(path.read_text(encoding="utf-8")) if path.exists() else {}


def for_symbol(research: dict[str, dict], symbol: str) -> dict | None:
    """This stock's research, tagged with its provenance, or None."""
    r = research.get(symbol.upper().removesuffix(".NS"))
    if not r:
        return None
    return {"provenance": "DeepSeek chat with web search, pasted by the user. UNVERIFIED: check every claim "
                          "against other inputs; chatbots can invent headlines and dates.", **r}
