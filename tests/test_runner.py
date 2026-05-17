from unittest.mock import MagicMock, patch
from bot.runner import run_cycle, RunSummary
from bot.scanner import SignalResult
from bot.news import NewsItem
from bot.llm import LLMDecision, Action
from bot.risk import OrderRequest, RejectionReason
from bot.trader import TradeResult


def _signal(ticker="AAPL"):
    return SignalResult(ticker=ticker, close=150.0, rsi=30.0,
                        signals=["RSI_OVERSOLD(30.0)"], passes_filter=True)


def _news_items(high_impact=False):
    return [NewsItem(headline="Apple earnings beat", score=3, high_impact=high_impact)]


def _decision(action=Action.BUY, ticker="AAPL"):
    return LLMDecision(action=action, ticker=ticker, confidence=0.85, reasoning="Strong signal")


def _approved_order(ticker="AAPL"):
    return OrderRequest(ticker=ticker, approved=True, qty=5, stop_price=142.5)


def _rejected_order(ticker="AAPL", reason=RejectionReason.MAX_POSITIONS_REACHED):
    return OrderRequest(ticker=ticker, approved=False, rejection=reason)


class TestRunCycle:
    def _patches(self):
        return {
            "scan":     patch("bot.runner.scan_watchlist",  return_value=[_signal()]),
            "news":     patch("bot.runner.classify_news",   return_value=_news_items()),
            "decision": patch("bot.runner.get_decision",    return_value=_decision()),
            "risk":     patch("bot.runner.validate_order",  return_value=_approved_order()),
            "trade":    patch("bot.runner.execute_order",   return_value=TradeResult("AAPL", True, "b1", "s1")),
            "account":  patch("bot.runner.get_account"),
            "positions":patch("bot.runner.get_positions",   return_value=[]),
        }

    def test_returns_run_summary(self):
        with self._patches()["scan"], self._patches()["news"], \
             self._patches()["decision"], self._patches()["risk"], \
             self._patches()["trade"], self._patches()["account"], \
             self._patches()["positions"]:
            summary = run_cycle(watchlist=["AAPL"], config={"api_key": "k", "alpaca_key": "a", "alpaca_secret": "s"})

        assert isinstance(summary, RunSummary)

    def test_trade_executed_on_buy_decision(self):
        trade_mock = MagicMock(return_value=TradeResult("AAPL", True, "b1", "s1"))
        with self._patches()["scan"], self._patches()["news"], \
             self._patches()["decision"], self._patches()["risk"], \
             patch("bot.runner.execute_order", trade_mock), \
             self._patches()["account"], self._patches()["positions"]:
            run_cycle(watchlist=["AAPL"], config={"api_key": "k", "alpaca_key": "a", "alpaca_secret": "s"})

        trade_mock.assert_called_once()

    def test_no_trade_when_llm_says_hold(self):
        trade_mock = MagicMock()
        with self._patches()["scan"], self._patches()["news"], \
             patch("bot.runner.get_decision", return_value=_decision(action=Action.HOLD)), \
             self._patches()["risk"], \
             patch("bot.runner.execute_order", trade_mock), \
             self._patches()["account"], self._patches()["positions"]:
            run_cycle(watchlist=["AAPL"], config={"api_key": "k", "alpaca_key": "a", "alpaca_secret": "s"})

        trade_mock.assert_not_called()

    def test_no_trade_when_risk_rejected(self):
        trade_mock = MagicMock()
        with self._patches()["scan"], self._patches()["news"], \
             self._patches()["decision"], \
             patch("bot.runner.validate_order", return_value=_rejected_order()), \
             patch("bot.runner.execute_order", trade_mock), \
             self._patches()["account"], self._patches()["positions"]:
            run_cycle(watchlist=["AAPL"], config={"api_key": "k", "alpaca_key": "a", "alpaca_secret": "s"})

        trade_mock.assert_not_called()

    def test_summary_records_analysed_tickers(self):
        with self._patches()["scan"], self._patches()["news"], \
             self._patches()["decision"], self._patches()["risk"], \
             self._patches()["trade"], self._patches()["account"], \
             self._patches()["positions"]:
            summary = run_cycle(watchlist=["AAPL"], config={"api_key": "k", "alpaca_key": "a", "alpaca_secret": "s"})

        assert "AAPL" in summary.analysed

    def test_no_trade_when_no_signal(self):
        trade_mock = MagicMock()
        with patch("bot.runner.scan_watchlist", return_value=[]), \
             self._patches()["news"], self._patches()["decision"], \
             self._patches()["risk"], patch("bot.runner.execute_order", trade_mock), \
             self._patches()["account"], self._patches()["positions"]:
            run_cycle(watchlist=["AAPL"], config={"api_key": "k", "alpaca_key": "a", "alpaca_secret": "s"})

        trade_mock.assert_not_called()
