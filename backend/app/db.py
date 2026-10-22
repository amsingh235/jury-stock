"""SQLite persistence (local stand-in for Supabase)."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    sector TEXT,
    price REAL,
    market_cap_cr REAL,
    avg_volume REAL,
    liquidity_pct REAL,
    fundamentals_pct REAL,
    composite REAL,
    rank INTEGER,
    screened_at TEXT
);
"""


def db_path() -> Path:
    """SQLite file from DATABASE_URL (sqlite:///path) or the default jury.db at the repo root."""
    url = os.environ.get("DATABASE_URL", "sqlite:///jury.db")
    p = Path(url.removeprefix("sqlite:///"))
    return p if p.is_absolute() else REPO_ROOT / p


def connect() -> sqlite3.Connection:
    """Open the database and make sure the schema exists."""
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
