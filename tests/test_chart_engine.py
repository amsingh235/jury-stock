"""Chart engine tests on synthetic OHLCV with known shapes."""
import json

import numpy as np
import pandas as pd
import pytest

from backend.app.services import chart_engine as ce


def make_ohlcv(path: list[tuple[int, float]], noise: float = 0.002, seed: int = 0) -> pd.DataFrame:
    """Build daily OHLCV by linearly joining (bars, price) waypoints, plus small noise."""
    rng = np.random.default_rng(seed)
    closes = [path[0][1]]
    for bars, target in path[1:]:
        closes += list(np.linspace(closes[-1], target, bars + 1)[1:])
    c = np.array(closes) * (1 + rng.normal(0, noise, len(closes)))
    idx = pd.bdate_range("2023-01-02", periods=len(c))
    return pd.DataFrame({
        "Open": c * (1 - noise), "High": c * 1.005, "Low": c * 0.995, "Close": c,
        "Volume": rng.integers(200_000, 400_000, len(c)).astype(float),
    }, index=idx)


def names(df: pd.DataFrame) -> set[str]:
    """Pattern keys detected in ``df``."""
    return {p["pattern"] for p in ce.analyze(df)["patterns_found"]}


def test_rsi_extremes():
    """RSI is 100 on a pure uptrend and near 0 on a pure downtrend."""
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert ce.rsi(up).iloc[-1] == pytest.approx(100)
    assert ce.rsi(up[::-1].reset_index(drop=True)).iloc[-1] < 1


def test_atr_constant_range():
    """ATR converges to the bar range when every bar has the same range and no gaps."""
    df = pd.DataFrame({"High": [11.0] * 50, "Low": [9.0] * 50, "Close": [10.0] * 50})
    assert ce.atr(df).iloc[-1] == pytest.approx(2.0)


def test_macd_and_bollinger_shapes():
    """MACD is positive in an uptrend and price stays inside bands on a gentle trend."""
    close = pd.Series(np.linspace(50, 100, 120))
    assert ce.macd(close)["macd"].iloc[-1] > 0
    bb = ce.bollinger(close)
    assert bb["lower"].iloc[-1] < close.iloc[-1] < bb["upper"].iloc[-1] + 1e-9


def test_psar_flips_below_price_in_uptrend():
    """Parabolic SAR sits below price after a sustained rise."""
    df = make_ohlcv([(0, 50), (80, 100)])
    assert ce.parabolic_sar(df).iloc[-1] < df["Close"].iloc[-1]


def test_adx_strong_in_trend():
    """ADX reads above 25 in a steady trend."""
    df = make_ohlcv([(0, 50), (120, 120)])
    assert ce.adx(df)["adx"].iloc[-1] > 25


def test_head_shoulders_top():
    """Left shoulder, higher head, matching right shoulder, then a neckline break."""
    df = make_ohlcv([(0, 80), (30, 100), (15, 90), (15, 110), (15, 90), (15, 100), (15, 85)])
    assert "head_shoulders_top" in names(df)


def test_inverse_head_shoulders():
    """Mirror image of the top pattern."""
    df = make_ohlcv([(0, 120), (30, 100), (15, 110), (15, 90), (15, 110), (15, 100), (15, 115)])
    assert "head_shoulders_bottom" in names(df)


def test_double_bottom():
    """Two lows at the same level separated by a 10%+ rally."""
    df = make_ohlcv([(0, 120), (30, 100), (20, 112), (20, 100), (20, 116)])
    assert "double_bottom" in names(df)


def test_double_top():
    """Two highs at the same level separated by a 10%+ decline."""
    df = make_ohlcv([(0, 80), (30, 100), (20, 88), (20, 100), (20, 84)])
    assert "double_top" in names(df)


def test_ascending_triangle():
    """Flat highs with rising lows."""
    df = make_ohlcv([(0, 85), (20, 100), (12, 88), (12, 100), (12, 92), (12, 100), (12, 95), (6, 98)])
    assert "ascending_triangle" in names(df)


def test_bull_flag():
    """A 20% pole in 10 bars then a tight downward drift."""
    df = make_ohlcv([(0, 100), (60, 100), (10, 125), (10, 121)], noise=0.001)
    assert "bull_flag" in names(df)


def test_cup_with_handle():
    """Rounded 25% cup between equal rims, then a shallow handle."""
    df = make_ohlcv([(0, 80), (30, 100), (25, 78), (20, 76), (25, 100), (8, 94)], noise=0.001)
    assert "cup_with_handle" in names(df)


def test_no_patterns_in_noise_is_allowed_and_output_is_json():
    """Random walk output is JSON-serialisable and every pattern carries Bulkowski stats."""
    rng = np.random.default_rng(1)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
    df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c,
                       "Volume": np.full(300, 1e6)}, index=pd.bdate_range("2022-01-03", periods=300))
    out = ce.analyze(df)
    json.dumps(out)
    for p in out["patterns_found"]:
        assert p["bulkowski"]["failure_rate_pct"] is not None and p["bulkowski"]["verified"] is False
    assert {"indicators", "trend", "support_resistance", "volume"} <= set(out)
    assert out["data_gaps"] == []


def test_short_history_reports_gap():
    """Too few bars returns a data gap instead of guessing."""
    df = make_ohlcv([(0, 50), (30, 60)])
    assert ce.analyze(df)["data_gaps"]


def test_false_positive_rate_on_random_walks():
    """No pattern fires on more than 15% of pure random walks."""
    import collections

    counts = collections.Counter()
    walks = 100
    for seed in range(walks):
        rng = np.random.default_rng(seed)
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 300)))
        df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c,
                           "Volume": np.full(300, 1e6)}, index=pd.bdate_range("2022-01-03", periods=300))
        counts.update(p["pattern"] for p in ce.analyze(df)["patterns_found"])
    worst = max(counts.values(), default=0)
    assert worst / walks <= 0.15, counts
