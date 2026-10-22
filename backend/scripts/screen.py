"""Run SCREEN mode: build the 50-stock watchlist and store it in SQLite."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.data.screener import screen  # noqa: E402


def main() -> None:
    """Screen NSE and print the ranked watchlist."""
    df = screen()
    cols = ["rank", "symbol", "name", "price", "market_cap_cr", "avg_volume", "composite"]
    print(df[[c for c in cols if c in df]].to_string(index=False))


if __name__ == "__main__":
    main()
