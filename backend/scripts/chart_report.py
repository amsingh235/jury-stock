"""Print the chart engine's output for one or more NSE tickers, e.g. IDEA SUZLON YESBANK."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.data.market import get_ohlcv  # noqa: E402
from backend.app.services.chart_engine import analyze  # noqa: E402


def main(symbols: list[str]) -> None:
    """Fetch two years of daily data per symbol and dump the rule-engine JSON."""
    for sym in symbols or ["IDEA"]:
        print(f"===== {sym} =====")
        print(json.dumps(analyze(get_ohlcv(sym)), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
