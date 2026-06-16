# tests/test_runner.py
from unittest.mock import MagicMock, patch
from bot.runner import run_cycle, RunSummary
from bot.scanner import SignalResult
from bot.news import NewsItem
from bot.llm import LLMDecision, Action
from bot.risk import OrderRequest, RejectionReason
from bot.trader import TradeResult


def _signal(ticker="AAPL"):
    return SignalResult(ticker=ticker, close=150.0, rsi=30.0, atr=1.5,
                        signals=["RSI_OVERSOLD(30.0)"], passes_filter=True)


def _news_items(high_impact=False):
    return [NewsItem(headline="Apple earnings beat", score=3, high_impact=high_impact)]


def _mock_provider(action=Action.BUY, ticker="AAPL"):
    provider = MagicMock()
    provider.get_decision.return_value = LLMDecision(
        action=action, ticker=ticker, confidence=0.85, reasoning="Strong signal"
    )
    return provider


def _approved_order(ticker="AAPL"):
    return OrderRequest(ticker=ticker, approved=True, qty=5, stop_price=142.5)


def _rejected_order(ticker="AAPL", reason=RejectionReason.MAX_POSITIONS_REACHED):
    return OrderRequest(ticker=ticker, approved=False, rejection=reason)


_CONFIG = {"llm_provider": "groq", "groq_api_key": "k", "alpaca_key": "a", "alpaca_secret": "s"}


class TestRunCycle:
    def _patches(self, provider=None):
        if provider is None:
            provider = _mock_provider()
        return {
            "scan":     patch("bot.runner.scan_watchlist",    return_value=[_signal()]),
            "news":     patch("bot.runner.classify_news",     return_value=_news_items(high_impact=True)),
            "llm":      patch("bot.runner.get_llm_provider",  return_value=provider),
            "risk":     patch("bot.runner.validate_order",    return_value=_approved_order()),
            "trade":    patch("bot.runner.execute_order",     return_value=TradeResult("AAPL", True, "b1", "s1")),
            "account":  patch("bot.runner.get_account"),
            "positions":patch("bot.runner.get_positions",     return_value=[]),
        }

    def test_returns_run_summary(self):
        p = self._patches()
        with p["scan"], p["news"], p["llm"], p["risk"], p["trade"], p["account"], p["positions"]:
            summary = run_cycle(watchlist=["AAPL"], config=_CONFIG)
        assert isinstance(summary, RunSummary)

    def test_trade_executed_on_buy_decision(self):
        trade_mock = MagicMock(return_value=TradeResult("AAPL", True, "b1", "s1"))
        p = self._patches()
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        trade_mock.assert_called_once()

    def test_no_trade_when_llm_says_hold(self):
        trade_mock = MagicMock()
        p = self._patches(provider=_mock_provider(action=Action.HOLD))
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_no_trade_when_risk_rejected(self):
        trade_mock = MagicMock()
        p = self._patches()
        with p["scan"], p["news"], p["llm"], \
             patch("bot.runner.validate_order", return_value=_rejected_order()), \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_summary_records_analysed_tickers(self):
        p = self._patches()
        with p["scan"], p["news"], p["llm"], p["risk"], p["trade"], p["account"], p["positions"]:
            summary = run_cycle(watchlist=["AAPL"], config=_CONFIG)
        assert "AAPL" in summary.analysed

    def test_no_trade_when_no_signal(self):
        trade_mock = MagicMock()
        p = self._patches()
        with patch("bot.runner.scan_watchlist", return_value=[]), \
             p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_only_high_impact_headlines_sent_to_llm(self):
        provider = _mock_provider()
        low  = NewsItem(headline="Noise headline", score=1, high_impact=False)
        high = NewsItem(headline="Apple acquisition", score=8, high_impact=True)
        p = self._patches(provider=provider)
        with p["scan"], \
             patch("bot.runner.classify_news", return_value=[low, high]), \
             p["llm"], p["risk"], p["trade"], p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        call_kwargs = provider.get_decision.call_args[1]
        assert call_kwargs["headlines"] == ["Apple acquisition"]
        assert "Noise headline" not in call_kwargs["headlines"]
