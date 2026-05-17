import pandas as pd
import pytest
from unittest.mock import patch
from bot.scanner import compute_signals, scan_watchlist


# --- helpers ---------------------------------------------------------------

def _prices(values: list[float]) -> pd.DataFrame:
    """Construit un DataFrame OHLCV minimal à partir d'une série de clôtures."""
    dates = pd.date_range(end=pd.Timestamp.today(), periods=len(values), freq="B")
    return pd.DataFrame({
        "Open":   values,
        "High":   [v + 0.5 for v in values],
        "Low":    [v - 0.5 for v in values],
        "Close":  values,
        "Volume": [2_000_000] * len(values),
    }, index=dates)


def _declining(n=30, start=100.0, step=1.0) -> pd.DataFrame:
    """30 jours de baisse continue → RSI très bas (oversold)."""
    return _prices([start - i * step for i in range(n)])


def _rising(n=30, start=50.0, step=1.0) -> pd.DataFrame:
    """30 jours de hausse continue → RSI très haut (overbought)."""
    return _prices([start + i * step for i in range(n)])


def _flat(n=30, price=100.0) -> pd.DataFrame:
    """Prix stables → RSI ~50, pas de signal."""
    return _prices([price] * n)


def _volume_spike(n=30, price=100.0) -> pd.DataFrame:
    """Volume du dernier jour 3× la moyenne → VOL_SPIKE."""
    df = _flat(n, price)
    avg = df["Volume"].mean()
    df.iloc[-1, df.columns.get_loc("Volume")] = int(avg * 3)
    return df


# --- compute_signals -------------------------------------------------------

class TestComputeSignals:
    def test_oversold_ticker_passes_filter(self):
        result = compute_signals(_declining(), "AAPL")
        assert result.passes_filter
        assert any("RSI_OVERSOLD" in s for s in result.signals)

    def test_overbought_ticker_passes_filter(self):
        result = compute_signals(_rising(), "AAPL")
        assert result.passes_filter
        assert any("RSI_OVERBOUGHT" in s for s in result.signals)

    def test_flat_ticker_is_blocked(self):
        result = compute_signals(_flat(), "MSFT")
        assert not result.passes_filter
        assert result.signals == []

    def test_volume_spike_passes_filter(self):
        result = compute_signals(_volume_spike(), "WMT")
        assert result.passes_filter
        assert any("VOL_SPIKE" in s for s in result.signals)

    def test_result_carries_ticker_and_close(self):
        df = _flat(price=123.45)
        result = compute_signals(df, "KO")
        assert result.ticker == "KO"
        assert result.close == pytest.approx(123.45, rel=1e-3)


# --- scan_watchlist --------------------------------------------------------

class TestScanWatchlist:
    def test_returns_only_tickers_with_signal(self):
        with patch("bot.scanner.fetch_ohlcv") as mock_fetch:
            mock_fetch.side_effect = lambda t: _declining() if t == "AAPL" else _flat()
            results = scan_watchlist(["AAPL", "MSFT"])

        assert len(results) == 1
        assert results[0].ticker == "AAPL"

    def test_skips_ticker_when_fetch_returns_none(self):
        with patch("bot.scanner.fetch_ohlcv") as mock_fetch:
            mock_fetch.return_value = None
            results = scan_watchlist(["AAPL"])

        assert results == []
