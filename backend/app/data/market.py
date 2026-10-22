"""yfinance wrappers for NSE stocks, with a per-day disk cache and retries."""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = REPO_ROOT / "data" / "cache"
OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]

# yfinance .info keys the fundamentals agent and screener use.
INFO_KEYS = [
    "longName", "sector", "industry", "currentPrice", "marketCap", "trailingPE", "priceToBook",
    "enterpriseToEbitda", "returnOnEquity", "returnOnAssets", "profitMargins", "grossMargins",
    "operatingMargins", "revenueGrowth", "earningsGrowth", "debtToEquity", "currentRatio",
    "totalRevenue", "freeCashflow", "operatingCashflow", "beta", "averageVolume",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "sharesOutstanding", "exDividendDate",
]


class MarketDataError(RuntimeError):
    """Raised when market data cannot be fetched after retries."""


def to_nse(symbol: str) -> str:
    """Normalise a symbol to its yfinance NSE form, e.g. 'idea' -> 'IDEA.NS'; indices like ^NSEI pass through."""
    s = symbol.strip().upper()
    return s if s.startswith("^") or s.endswith((".NS", ".BO")) else f"{s}.NS"


def _retry(fn, attempts: int = 3, base_delay: float = 2.0):
    """Call ``fn`` with exponential backoff; raise MarketDataError if every attempt fails."""
    err = None
    for k in range(attempts):
        try:
            return fn()
        except Exception as e:  # yfinance raises many unrelated exception types
            err = e
            time.sleep(base_delay * 2 ** k)
    raise MarketDataError(str(err)) from err


def _cache_path(kind: str, key: str) -> Path:
    """Path of today's cache file for ``kind``/``key``."""
    return CACHE_DIR / kind / f"{key}_{date.today().isoformat()}.pkl"


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance's column layout, keep OHLCV, drop empty rows, make the index tz-naive."""
    if isinstance(df.columns, pd.MultiIndex):
        lvl = next(i for i in range(df.columns.nlevels)
                   if set(OHLCV_COLS) & set(df.columns.get_level_values(i)))
        df.columns = df.columns.get_level_values(lvl)
    df = df[[c for c in OHLCV_COLS if c in df.columns]].dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[df["Volume"] > 0] if "Volume" in df else df


def get_ohlcv(symbol: str, period: str = "2y", use_cache: bool = True) -> pd.DataFrame:
    """Daily OHLCV for one NSE stock (auto-adjusted), cached for the day."""
    import yfinance as yf

    sym = to_nse(symbol)
    path = _cache_path("ohlcv", f"{sym}_{period}")
    if use_cache and path.exists():
        return pd.read_pickle(path)
    df = _retry(lambda: yf.Ticker(sym).history(period=period, auto_adjust=True))
    if df is None or df.empty:
        raise MarketDataError(f"No price data for {sym}")
    df = clean_ohlcv(df)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(path)
    return df


def get_ohlcv_batch(symbols: list[str], period: str = "3mo") -> dict[str, pd.DataFrame]:
    """Download OHLCV for many symbols in one yfinance call; skips symbols with no data."""
    import yfinance as yf

    syms = [to_nse(s) for s in symbols]
    raw = _retry(lambda: yf.download(syms, period=period, group_by="ticker", auto_adjust=True,
                                     threads=True, progress=False))
    out = {}
    for s in syms:
        try:
            df = clean_ohlcv(raw[s].copy() if len(syms) > 1 else raw.copy())
        except KeyError:
            continue
        if not df.empty:
            out[s] = df
    return out


def get_info(symbol: str, use_cache: bool = True) -> dict:
    """Selected fundamentals from yfinance ``.info`` (missing keys become None), cached for the day."""
    import yfinance as yf

    sym = to_nse(symbol)
    path = _cache_path("info", sym)
    if use_cache and path.exists():
        return pd.read_pickle(path)
    info = _retry(lambda: yf.Ticker(sym).info) or {}
    out = {k: info.get(k) for k in INFO_KEYS}
    out["symbol"] = sym
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(out, path)
    return out


def get_financials(symbol: str) -> dict[str, pd.DataFrame]:
    """Annual income statement, balance sheet and cash flow (empty frames when unavailable)."""
    import yfinance as yf

    t = yf.Ticker(to_nse(symbol))
    return {
        "income": _retry(lambda: t.financials),
        "balance": _retry(lambda: t.balance_sheet),
        "cashflow": _retry(lambda: t.cashflow),
    }
