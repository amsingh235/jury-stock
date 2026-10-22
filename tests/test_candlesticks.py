"""Candlestick detection on hand-built bars."""
import pandas as pd

from backend.app.services import candlesticks as cs


def frame(bars):
    """OHLC bars -> DataFrame with constant volume."""
    df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close"])
    df["Volume"] = 1e6
    df.index = pd.bdate_range("2026-01-01", periods=len(df))
    return df


def down(n=12, start=120.0, step=2.0):
    """A falling run of ordinary candles."""
    out, p = [], start
    for _ in range(n):
        out.append((p, p + 0.5, p - step - 0.5, p - step))
        p -= step
    return out


def up(n=12, start=80.0, step=2.0):
    """A rising run of ordinary candles."""
    out, p = [], start
    for _ in range(n):
        out.append((p, p + step + 0.5, p - 0.5, p + step))
        p += step
    return out


def last(df):
    """Patterns completing on the final bar."""
    return cs.patterns_at(df, len(df) - 1)


def test_hammer_needs_downtrend_and_long_lower_shadow():
    """Same shape is a hammer after a fall and a hanging man after a rise."""
    assert "hammer" in last(frame(down() + [(95.5, 96.6, 90.0, 96.4)]))
    assert "hanging_man" in last(frame(up() + [(103.5, 104.6, 98.0, 104.4)]))


def test_shooting_star_after_rise():
    """Long upper shadow at the top of an uptrend."""
    assert "shooting_star" in last(frame(up() + [(104.5, 110.0, 104.0, 105.2)]))


def test_engulfing_pair():
    """Bullish engulfing after a fall; bearish engulfing after a rise."""
    assert "bullish_engulfing" in last(frame(down() + [(96.0, 96.5, 93.0, 93.5), (93.0, 97.5, 92.5, 97.0)]))
    assert "bearish_engulfing" in last(frame(up() + [(104.0, 107.0, 103.5, 106.5), (107.0, 107.5, 103.0, 103.5)]))


def test_morning_star():
    """Big down candle, small gapped-down star, strong up close past the midpoint."""
    bars = down() + [(96.0, 96.5, 90.5, 91.0), (89.5, 90.0, 88.5, 89.0), (89.5, 95.5, 89.0, 95.0)]
    assert "morning_star" in last(frame(bars))


def test_three_white_soldiers():
    """Three long up candles, each opening inside the last and closing higher."""
    bars = down(8) + [(104.0, 107.2, 103.8, 107.0), (105.5, 110.2, 105.3, 110.0), (108.5, 113.2, 108.3, 113.0)]
    assert "three_white_soldiers" in last(frame(bars))


def test_doji_and_detect_context():
    """A doji is found and detect() reports trend, bars_ago and nearby levels."""
    df = frame(down() + [(96.0, 97.0, 95.0, 96.02)])
    out = cs.detect(df, levels=[{"type": "support", "level": 95.2}], atr=1.0)
    hit = [p for p in out if p["pattern"] == "doji"][0]
    assert hit["bars_ago"] == 0 and hit["prior_trend"] == "down" and hit["near_level"] == ["support 95.2"]


def test_ordinary_trend_has_no_reversal_patterns():
    """Plain trending candles trigger nothing."""
    assert not any(cs.patterns_at(frame(up(20)), i) for i in range(12, 20))
