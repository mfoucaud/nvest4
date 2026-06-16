import pandas as pd
import pytest
from unittest.mock import patch
from bot.market_regime import get_market_regime, MarketRegime


def _spy_df(closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.today(), periods=len(closes), freq="B")
    return pd.DataFrame({
        "Open": closes, "High": [c + 1 for c in closes],
        "Low": [c - 1 for c in closes], "Close": closes,
        "Volume": [1_000_000] * len(closes),
    }, index=dates)


def _bull_spy() -> pd.DataFrame:
    """Prix croissant sur 250 jours → EMA50 et EMA200 en uptrend, prix > EMA50 > EMA200."""
    closes = [100.0 + i * 0.5 for i in range(250)]
    return _spy_df(closes)


def _bear_spy() -> pd.DataFrame:
    """Prix décroissant sur 250 jours → prix < EMA50 < EMA200."""
    closes = [225.0 - i * 0.5 for i in range(250)]
    return _spy_df(closes)


def _neutral_spy() -> pd.DataFrame:
    """Prix oscillant → NEUTRAL."""
    import math
    closes = [150.0 + 10 * math.sin(i * 0.1) for i in range(250)]
    return _spy_df(closes)


class TestGetMarketRegime:
    def test_bull_market_detected(self):
        with patch("bot.market_regime.fetch_spy") as mock:
            mock.return_value = _bull_spy()
            result = get_market_regime()
        assert result.regime == "BULL"

    def test_bear_market_detected(self):
        with patch("bot.market_regime.fetch_spy") as mock:
            mock.return_value = _bear_spy()
            result = get_market_regime()
        assert result.regime == "BEAR"

    def test_returns_market_regime_dataclass(self):
        with patch("bot.market_regime.fetch_spy") as mock:
            mock.return_value = _bull_spy()
            result = get_market_regime()
        assert isinstance(result, MarketRegime)
        assert isinstance(result.spy_perf_5d, float)

    def test_spy_perf_5d_is_correct(self):
        closes = [100.0 + i * 0.5 for i in range(250)]
        df = _spy_df(closes)
        with patch("bot.market_regime.fetch_spy") as mock:
            mock.return_value = df
            result = get_market_regime()
        # perf 5j = (close[-1] - close[-6]) / close[-6] * 100
        expected = (closes[-1] - closes[-6]) / closes[-6] * 100
        assert result.spy_perf_5d == pytest.approx(expected, rel=1e-3)

    def test_fallback_neutral_when_fetch_fails(self):
        with patch("bot.market_regime.fetch_spy", return_value=None):
            result = get_market_regime()
        assert result.regime == "NEUTRAL"
        assert result.spy_perf_5d == 0.0
