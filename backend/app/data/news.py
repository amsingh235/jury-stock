"""Headlines and event candidates for the sentiment and news agents.

Sources: yfinance's news feed (via Yahoo) and Google News RSS where reachable;
events add yfinance's earnings calendar and corporate actions. Headlines are
tagged with event types by keyword so the news agent gets structured candidates.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import httpx
import pandas as pd

from .market import to_nse

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"

EVENT_KEYWORDS = {
    "earnings": r"\b(q[1-4]|quarter|results?|profit|loss|revenue|earnings|ebitda)\b",
    "buyback": r"\bbuy-?back\b",
    "promoter": r"\bpromoter|stake (sale|buy)|pledge",
    "rating": r"\b(upgrade|downgrade|rating|crisil|icra|moody|fitch|s&p)\b",
    "regulatory": r"\b(sebi|rbi|penalty|probe|ban|regulator|court|tribunal|nclt|fine)\b",
    "corporate_action": r"\b(dividend|split|bonus|rights issue|merger|acquisition|demerger|fund ?rais|qip|fpo)\b",
    "rumor": r"\b(report(edly|s say)|sources said|likely to|in talks|rumou?r|buzz)\b",
}


def _yf_items(raw: list[dict], require_ticker: str | None = None) -> list[dict]:
    """Normalise yfinance news items to title/published/source.

    With ``require_ticker``, keep only items whose relatedTickers include it (bare-symbol
    searches like 'IDEA' otherwise match unrelated stories).
    """
    items = []
    for n in raw or []:
        c = n.get("content", n)
        title = c.get("title")
        if not title:
            continue
        if require_ticker and require_ticker not in (n.get("relatedTickers") or c.get("relatedTickers") or []):
            continue
        when = c.get("pubDate") or c.get("providerPublishTime")
        if isinstance(when, (int, float)):
            when = datetime.fromtimestamp(when, timezone.utc).isoformat()
        prov = c.get("provider", {})
        source = (prov.get("displayName") if isinstance(prov, dict) else None) or c.get("publisher") or "Yahoo"
        items.append({"title": title, "published": when, "source": source})
    return items


def short_name(company: str | None) -> str | None:
    """Company name without legal suffixes, e.g. 'Vodafone Idea Limited' -> 'Vodafone Idea'."""
    if not company:
        return None
    return re.sub(r"\b(private\s+limited|limited|ltd\.?|pvt\.?)\s*$", "",
                  company.strip(), flags=re.I).strip(" ,.") or company


def _yf_news(symbol: str, company: str | None = None) -> list[dict]:
    """Headlines from yfinance: the ticker feed, Yahoo search by bare symbol (ticker-matched) and by name.

    ``Ticker.news`` is usually empty for NSE stocks, so search fills the gap.
    """
    import yfinance as yf

    sym = to_nse(symbol)
    items = _yf_items(yf.Ticker(sym).news)
    items += _yf_items(yf.Search(sym.removesuffix(".NS"), news_count=20).news, require_ticker=sym)
    name = short_name(company)
    if name:
        items += _yf_items(yf.Search(name, news_count=20).news)
    return items


def _google_news(query: str) -> list[dict]:
    """Headlines from Google News RSS for ``query``."""
    r = httpx.get(GOOGLE_NEWS.format(q=quote_plus(query)), timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    items = []
    for it in ET.fromstring(r.text).iter("item"):
        title = (it.findtext("title") or "").strip()
        src = it.findtext("source") or (title.rsplit(" - ", 1)[-1] if " - " in title else "Google News")
        pub = it.findtext("pubDate")
        items.append({"title": title, "published": parsedate_to_datetime(pub).isoformat() if pub else None, "source": src})
    return items


def sanitize(text: str, limit: int = 300) -> str:
    """Untrusted feed text: drop control characters and markup brackets, collapse whitespace, cap length."""
    text = re.sub(r"[\x00-\x1f\x7f<>{}]", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def get_headlines(symbol: str, company: str | None = None, limit: int = 30) -> tuple[list[dict], list[str]]:
    """Deduplicated recent headlines plus a list of sources that failed."""
    found, failed = [], []
    for name, fn in (("yfinance", lambda: _yf_news(symbol, company)),
                     ("google_news", lambda: _google_news(f"{company or symbol} NSE share"))):
        try:
            found += fn()
        except Exception as e:  # each feed fails in its own way; record and move on
            failed.append(f"{name}: {type(e).__name__}")
    for h in found:
        h["title"] = sanitize(h["title"])
        h["source"] = sanitize(h.get("source") or "unknown", 60)
    seen, out = set(), []
    for h in sorted(found, key=lambda h: h.get("published") or "", reverse=True):
        key = re.sub(r"\W+", " ", h["title"].lower()).strip()[:80]
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out[:limit], failed


def tag_events(headline: str) -> list[str]:
    """Event types whose keywords appear in ``headline``."""
    return [k for k, pat in EVENT_KEYWORDS.items() if re.search(pat, headline, re.I)]


def get_event_candidates(symbol: str, headlines: list[dict]) -> tuple[list[dict], list[str]]:
    """Structured event candidates: earnings calendar, corporate actions and tagged headlines."""
    import yfinance as yf

    t = yf.Ticker(to_nse(symbol))
    events, gaps = [], []
    try:
        cal = t.calendar or {}
        for d in cal.get("Earnings Date", []) if isinstance(cal, dict) else []:
            events.append({"type": "earnings", "kind": "scheduled", "date": str(d),
                           "description": "Scheduled earnings date", "source": "yfinance calendar", "verified": True})
    except Exception as e:
        gaps.append(f"earnings calendar unavailable ({type(e).__name__})")
    try:
        actions = t.actions
        if actions is not None and not actions.empty:
            recent = actions[actions.index >= pd.Timestamp.now(tz=actions.index.tz) - pd.Timedelta(days=365)]
            for when, row in recent.iterrows():
                for col, label in (("Dividends", "dividend"), ("Stock Splits", "split")):
                    if row.get(col):
                        events.append({"type": "corporate_action", "kind": "scheduled", "date": str(when.date()),
                                       "description": f"{label} {row[col]}", "source": "yfinance actions", "verified": True})
    except Exception as e:
        gaps.append(f"corporate actions unavailable ({type(e).__name__})")
    for h in headlines:
        tags = tag_events(h["title"])
        if tags:
            events.append({"type": tags[0] if tags[0] != "rumor" else (tags[1] if len(tags) > 1 else "rumor"),
                           "kind": "rumor" if "rumor" in tags else "unscheduled", "date": h.get("published"),
                           "description": h["title"], "source": h["source"],
                           "verified": False})  # headlines are not exchange filings
    gaps.append("no exchange-filing feed in pipeline: headline events are unverified")
    return events, gaps


def get_catalysts(info: dict, events: list[dict], today: datetime | None = None) -> list[dict]:
    """Upcoming dated catalysts (catalyst-calendar pattern): scheduled events ahead, with days until.

    Adapted from the catalyst-calendar skill in anthropics/financial-services (Apache-2.0).
    """
    now = (today or datetime.now(timezone.utc)).date()
    out = []
    for e in events:
        if e["kind"] != "scheduled" or not e.get("date"):
            continue
        try:
            d = pd.Timestamp(e["date"]).date()
        except (ValueError, TypeError):
            continue
        if d >= now:
            out.append({"catalyst": e["description"], "date": str(d), "days_until": (d - now).days, "source": e["source"]})
    ex_div = info.get("exDividendDate")
    if isinstance(ex_div, (int, float)):
        d = datetime.fromtimestamp(ex_div, timezone.utc).date()
        if d >= now:
            out.append({"catalyst": "ex-dividend date", "date": str(d), "days_until": (d - now).days, "source": "yfinance info"})
    return sorted(out, key=lambda c: c["days_until"])
