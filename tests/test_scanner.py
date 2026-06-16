import pandas as pd
import pytest
from unittest.mock import patch
from bot.scanner import compute_signals, scan_watchlist, SignalResult


# --- helpers ---------------------------------------------------------------

def _prices(values: list[float], volumes: list[int] | None = None) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.today(), periods=len(values), freq="B")
    vols = volumes if volumes else [2_000_000] * len(values)
    return pd.DataFrame({
        "Open":   values,
        "High":   [v + 0.5 for v in values],
        "Low":    [v - 0.5 for v in values],
        "Close":  values,
        "Volume": vols,
    }, index=dates)


def _declining(n=60, start=100.0, step=1.0) -> pd.DataFrame:
    """60 jours de baisse → RSI oversold + EMA cross DOWN."""
    return _prices([start - i * step for i in range(n)])


def _rising(n=60, start=50.0, step=1.0) -> pd.DataFrame:
    """60 jours de hausse → RSI overbought + EMA cross UP."""
    return _prices([start + i * step for i in range(n)])


def _flat(n=60, price=100.0) -> pd.DataFrame:
    return _prices([price] * n)


def _strong_trend_up(n=60) -> pd.DataFrame:
    """Tendance haussière forte : RSI overbought + EMA_CROSS_UP + VOL_SPIKE + ADX élevé."""
    closes = [50.0 + i * 1.5 for i in range(n)]
    volumes = [2_000_000] * n
    volumes[-1] = 7_000_000  # volume spike
    return _prices(closes, volumes)


def _1h_df(trend: str, n: int = 200) -> pd.DataFrame:
    """DataFrame 1h simulé avec tendance UP ou DOWN."""
    if trend == "UP":
        closes = [100.0 + i * 0.1 for i in range(n)]
    else:
        closes = [120.0 - i * 0.1 for i in range(n)]
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="h")
    return pd.DataFrame({
        "Open": closes, "High": [c + 0.1 for c in closes],
        "Low": [c - 0.1 for c in closes], "Close": closes,
        "Volume": [500_000] * n,
    }, index=dates)


# --- compute_signals -------------------------------------------------------

class TestComputeSignals:
    def test_result_has_atr_field(self):
        result = compute_signals(_rising(), "AAPL", _1h_df("UP"))
        assert isinstance(result.atr, float)
        assert result.atr > 0

    def test_flat_ticker_fails_confluence(self):
        """Un actif plat ne génère pas 2 signaux → passes_filter=False."""
        result = compute_signals(_flat(), "MSFT", _1h_df("UP"))
        assert not result.passes_filter

    def test_strong_trend_passes_confluence(self):
        """Tendance forte → ≥2 signaux + ADX>25 → passes_filter=True."""
        result = compute_signals(_strong_trend_up(), "NVDA", _1h_df("UP"))
        assert result.passes_filter
        assert len(result.signals) >= 2

    def test_1h_trend_included_in_signals(self):
        result = compute_signals(_rising(), "AAPL", _1h_df("UP"))
        assert any("TREND_1H" in s for s in result.signals)

    def test_result_carries_ticker_and_close(self):
        df = _flat(price=123.45)
        result = compute_signals(df, "KO", _1h_df("UP"))
        assert result.ticker == "KO"
        assert result.close == pytest.approx(123.45, rel=1e-3)

    def test_single_signal_not_enough(self):
        """Un seul signal (ex: volume spike seul sur actif flat) → passes_filter=False."""
        n = 60
        vols = [2_000_000] * n
        vols[-1] = 7_000_000
        df = _prices([100.0] * n, vols)
        result = compute_signals(df, "XOM", _1h_df("UP"))
        # RSI sera ~50 (flat), pas d'EMA cross, pas de MACD signal → 1 seul signal
        # Confluence exige ≥2 → False
        assert not result.passes_filter


# --- scan_watchlist --------------------------------------------------------

class TestScanWatchlist:
    def test_returns_only_tickers_with_signal(self):
        with patch("bot.scanner.fetch_ohlcv", side_effect=lambda t: _strong_trend_up() if t == "NVDA" else _flat()), \
             patch("bot.scanner.fetch_ohlcv_1h", return_value=_1h_df("UP")):
            results = scan_watchlist(["NVDA", "MSFT"])
        assert len(results) == 1
        assert results[0].ticker == "NVDA"

    def test_skips_ticker_when_fetch_returns_none(self):
        with patch("bot.scanner.fetch_ohlcv", return_value=None), \
             patch("bot.scanner.fetch_ohlcv_1h", return_value=None):
            results = scan_watchlist(["AAPL"])
        assert results == []
