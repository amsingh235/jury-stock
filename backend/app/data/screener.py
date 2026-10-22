"""SCREEN mode (spec §7.1): deterministic NSE filter producing the 50-stock watchlist.

Pipeline: NSE equity list -> drop surveillance (ASM/GSM) and recent listings ->
batch price/volume filter -> market-cap filter -> rank by liquidity and
fundamentals percentiles. No LLM calls.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta

import pandas as pd
import requests
import yaml

from ..db import connect
from . import market

EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_HOME = "https://www.nseindia.com"
SURVEILLANCE_URLS = {
    "ASM": "https://www.nseindia.com/api/reportASM",
    "GSM": "https://www.nseindia.com/api/reportGSM",
}
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/csv,*/*", "Referer": NSE_HOME}
CONFIG_PATH = market.REPO_ROOT / "config" / "screen.yaml"

# Higher is better for these fundamentals; debt_to_equity is inverted before ranking.
FUNDAMENTAL_KEYS = ["returnOnEquity", "profitMargins", "revenueGrowth", "currentRatio", "debtToEquity"]


def load_config() -> dict:
    """Read the screening thresholds from config/screen.yaml."""
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _nse_session() -> requests.Session:
    """Session primed with NSE cookies (their API refuses cookieless requests)."""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(NSE_HOME, timeout=20)
    return s


def fetch_universe(session: requests.Session | None = None) -> pd.DataFrame:
    """NSE EQ-series listings with symbol, name and listing date."""
    s = session or _nse_session()
    r = s.get(EQUITY_LIST_URL, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.strip() for c in df.columns]
    df = df[df["SERIES"].str.strip() == "EQ"]
    return pd.DataFrame({
        "symbol": df["SYMBOL"].str.strip(),
        "name": df["NAME OF COMPANY"].str.strip(),
        "listed": pd.to_datetime(df["DATE OF LISTING"].str.strip(), format="%d-%b-%Y", errors="coerce"),
    })


def _symbols_from_json(obj) -> set[str]:
    """Collect every 'symbol' value from an arbitrarily nested NSE API response."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == "symbol" and isinstance(v, str):
                found.add(v.strip().upper())
            else:
                found |= _symbols_from_json(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _symbols_from_json(v)
    return found


def fetch_surveillance(session: requests.Session | None = None) -> tuple[set[str], list[str]]:
    """Symbols on NSE's ASM and GSM lists, plus a list of lists that could not be fetched."""
    s = session or _nse_session()
    symbols, failed = set(), []
    for name, url in SURVEILLANCE_URLS.items():
        try:
            r = s.get(url, timeout=30)
            r.raise_for_status()
            symbols |= _symbols_from_json(r.json())
        except (requests.RequestException, ValueError):
            failed.append(name)
    return symbols, failed


def prefilter(universe: pd.DataFrame, surveillance: set[str], min_listed_years: float,
              today: datetime | None = None) -> pd.DataFrame:
    """Drop surveillance-list stocks and anything listed for less than ``min_listed_years``."""
    cutoff = (today or datetime.now()) - timedelta(days=365.25 * min_listed_years)
    keep = ~universe["symbol"].str.upper().isin(surveillance) & (universe["listed"] <= cutoff)
    return universe[keep].reset_index(drop=True)


def price_volume_table(prices: dict[str, pd.DataFrame], lookback: int) -> pd.DataFrame:
    """Last close, average volume and average traded value per symbol over ``lookback`` bars."""
    rows = []
    for sym, df in prices.items():
        tail = df.tail(lookback)
        rows.append({
            "symbol": sym.removesuffix(".NS"),
            "price": float(tail["Close"].iloc[-1]),
            "avg_volume": float(tail["Volume"].mean()),
            "avg_traded_value": float((tail["Close"] * tail["Volume"]).mean()),
        })
    return pd.DataFrame(rows)


def apply_filters(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Keep rows passing the price, volume and (where known) market-cap thresholds."""
    ok = (df["price"] < cfg["max_price_inr"]) & (df["avg_volume"] > cfg["min_avg_daily_volume"])
    if "market_cap_cr" in df:
        ok &= df["market_cap_cr"] > cfg["min_market_cap_cr"]
    return df[ok].reset_index(drop=True)


def rank(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Score by liquidity and fundamentals percentiles and return the top_n, best first.

    Missing fundamentals rank at the bottom (0th percentile) rather than the median,
    so thinly reported stocks don't get the benefit of the doubt.
    """
    df = df.copy()
    df["liquidity_pct"] = df["avg_traded_value"].rank(pct=True) * 100
    parts = []
    for k in FUNDAMENTAL_KEYS:
        if k not in df:
            continue
        col = -df[k] if k == "debtToEquity" else df[k]
        parts.append(col.rank(pct=True).fillna(0) * 100)
    df["fundamentals_pct"] = pd.concat(parts, axis=1).mean(axis=1) if parts else 0.0
    w = cfg["rank_weights"]
    df["composite"] = w["liquidity"] * df["liquidity_pct"] + w["fundamentals"] * df["fundamentals_pct"]
    df = df.sort_values("composite", ascending=False).head(cfg["top_n"]).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df


def save_watchlist(df: pd.DataFrame) -> None:
    """Replace the watchlist table with the screened stocks."""
    now = datetime.now().isoformat(timespec="seconds")
    cols = ["symbol", "name", "sector", "price", "market_cap_cr", "avg_volume",
            "liquidity_pct", "fundamentals_pct", "composite", "rank"]
    with connect() as conn:
        conn.execute("DELETE FROM watchlist")
        conn.executemany(
            f"INSERT INTO watchlist ({','.join(cols)}, screened_at) VALUES ({','.join('?' * (len(cols) + 1))})",
            [tuple(None if pd.isna(r.get(c)) else r.get(c) for c in cols) + (now,) for r in df.to_dict("records")],
        )


def screen(save: bool = True, log=print) -> pd.DataFrame:
    """Run the full SCREEN pipeline and return the ranked watchlist."""
    cfg = load_config()
    session = _nse_session()
    universe = fetch_universe(session)
    surveillance, failed = fetch_surveillance(session)
    if failed:
        log(f"WARNING: could not fetch {', '.join(failed)} list(s); those stocks are NOT excluded")
    base = prefilter(universe, surveillance, cfg["min_listed_years"])
    log(f"Universe {len(universe)} -> {len(base)} after surveillance/listing-age filter")

    frames = []
    syms = base["symbol"].tolist()
    for i in range(0, len(syms), 200):
        frames.append(price_volume_table(market.get_ohlcv_batch(syms[i:i + 200], period="6mo"),
                                         cfg["lookback_days_volume"]))
        log(f"  prices {min(i + 200, len(syms))}/{len(syms)}")
    pv = apply_filters(pd.concat(frames, ignore_index=True), cfg)
    log(f"{len(pv)} pass price < {cfg['max_price_inr']} and volume > {cfg['min_avg_daily_volume']}")

    infos = []
    for n, sym in enumerate(pv["symbol"], 1):
        try:
            infos.append(market.get_info(sym))
        except market.MarketDataError as e:
            log(f"  skip {sym}: {e}")
        if n % 25 == 0:
            log(f"  fundamentals {n}/{len(pv)}")
    info = pd.DataFrame(infos)
    info["symbol"] = info["symbol"].str.removesuffix(".NS")
    info["market_cap_cr"] = info["marketCap"] / 1e7
    df = pv.merge(info.rename(columns={"longName": "name"}), on="symbol")
    df = apply_filters(df, cfg)
    log(f"{len(df)} pass market cap > Rs.{cfg['min_market_cap_cr']} Cr")
    ranked = rank(df, cfg)
    if save:
        save_watchlist(ranked)
    return ranked
