# tests/test_runner.py
import pytest
from unittest.mock import MagicMock, patch
from bot.runner import run_cycle, RunSummary, compute_trail_pct
from bot.scanner import SignalResult
from bot.news import NewsItem
from bot.llm import LLMDecision, Action
from bot.risk import OrderRequest, RejectionReason
from bot.trader import TradeResult
from bot.market_regime import MarketRegime


def _signal(ticker="NVDA", atr=5.0):
    return SignalResult(
        ticker=ticker, close=150.0, rsi=30.0, atr=atr,
        signals=["RSI_OVERSOLD(30.0)", "EMA_CROSS_UP"], passes_filter=True,
    )


def _news_items(high_impact=False):
    return [NewsItem(headline="NVDA earnings beat", score=3, high_impact=high_impact)]


def _mock_provider(action=Action.BUY, ticker="NVDA", confidence=0.85):
    provider = MagicMock()
    provider.get_decision.return_value = LLMDecision(
        action=action, ticker=ticker, confidence=confidence, reasoning="Strong signal"
    )
    return provider


def _approved_order(ticker="NVDA"):
    return OrderRequest(ticker=ticker, approved=True, qty=5, stop_price=142.5)


def _rejected_order(ticker="NVDA", reason=RejectionReason.MAX_POSITIONS_REACHED):
    return OrderRequest(ticker=ticker, approved=False, rejection=reason)


_CONFIG = {"llm_provider": "groq", "groq_api_key": "k", "alpaca_key": "a", "alpaca_secret": "s"}
_BULL = MarketRegime(regime="BULL", spy_perf_5d=1.5)
_BEAR = MarketRegime(regime="BEAR", spy_perf_5d=-2.0)
_NEUTRAL = MarketRegime(regime="NEUTRAL", spy_perf_5d=0.1)


class TestComputeTrailPct:
    def test_normal_case(self):
        # 2 * 5 / 150 * 100 = 6.67 → borné dans [3, 10]
        assert compute_trail_pct(atr=5.0, close=150.0) == 6.7

    def test_minimum_bound(self):
        # très faible ATR → minimum 3%
        assert compute_trail_pct(atr=0.1, close=150.0) == 3.0

    def test_maximum_bound(self):
        # ATR très élevé → maximum 10%
        assert compute_trail_pct(atr=50.0, close=100.0) == 10.0


class TestRunCycle:
    def _patches(self, provider=None, regime=None):
        if provider is None:
            provider = _mock_provider()
        if regime is None:
            regime = _BULL
        return {
            "scan":      patch("bot.runner.scan_watchlist",    return_value=[_signal()]),
            "news":      patch("bot.runner.classify_news",     return_value=_news_items(high_impact=True)),
            "llm":       patch("bot.runner.get_llm_provider",  return_value=provider),
            "risk":      patch("bot.runner.validate_order",    return_value=_approved_order()),
            "trade":     patch("bot.runner.execute_order",     return_value=TradeResult("NVDA", True, "b1", "s1")),
            "account":   patch("bot.runner.get_account"),
            "positions": patch("bot.runner.get_positions",     return_value=[]),
            "regime":    patch("bot.runner.get_market_regime", return_value=regime),
        }

    def test_returns_run_summary(self):
        p = self._patches()
        with p["scan"], p["news"], p["llm"], p["risk"], p["trade"], p["account"], p["positions"], p["regime"]:
            summary = run_cycle(watchlist=["NVDA"], config=_CONFIG)
        assert isinstance(summary, RunSummary)

    def test_trade_executed_on_buy_decision_in_bull(self):
        trade_mock = MagicMock(return_value=TradeResult("NVDA", True, "b1", "s1"))
        p = self._patches(regime=_BULL)
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        trade_mock.assert_called_once()

    def test_buy_blocked_in_bear_market(self):
        """BUY en régime BEAR → trade bloqué."""
        trade_mock = MagicMock()
        provider = _mock_provider(action=Action.BUY)
        p = self._patches(provider=provider, regime=_BEAR)
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_sell_blocked_in_bull_market(self):
        """SELL en régime BULL → trade bloqué avec raison REGIME_CONFLICT."""
        short_mock = MagicMock()
        provider = _mock_provider(action=Action.SELL)
        p = self._patches(provider=provider, regime=_BULL)
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_short_order", short_mock), p["account"], p["positions"], p["regime"]:
            summary = run_cycle(watchlist=["NVDA"], config=_CONFIG)
        short_mock.assert_not_called()
        assert any("REGIME_CONFLICT" in s.get("reason", "") for s in summary.skipped)

    def test_low_confidence_decision_skipped(self):
        """Confidence < 0.65 → trade skippé."""
        trade_mock = MagicMock()
        provider = _mock_provider(action=Action.BUY, confidence=0.5)
        p = self._patches(provider=provider, regime=_BULL)
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_no_trade_when_llm_says_hold(self):
        trade_mock = MagicMock()
        p = self._patches(provider=_mock_provider(action=Action.HOLD))
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_no_trade_when_risk_rejected(self):
        trade_mock = MagicMock()
        p = self._patches()
        with p["scan"], p["news"], p["llm"], \
             patch("bot.runner.validate_order", return_value=_rejected_order()), \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_trail_pct_uses_atr(self):
        """Le trailing stop passé à execute_order est calculé via ATR."""
        trade_mock = MagicMock(return_value=TradeResult("NVDA", True, "b1", "s1"))
        p = self._patches(regime=_BULL)
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        call_kwargs = trade_mock.call_args[1]
        # atr=5.0, close=150.0 → trail = 2*5/150*100 = 6.7%
        assert call_kwargs["trail_percent"] == pytest.approx(6.7, rel=1e-2)

    def test_summary_records_analysed_tickers(self):
        p = self._patches()
        with p["scan"], p["news"], p["llm"], p["risk"], p["trade"], p["account"], p["positions"], p["regime"]:
            summary = run_cycle(watchlist=["NVDA"], config=_CONFIG)
        assert "NVDA" in summary.analysed

    def test_no_trade_when_no_signal(self):
        """Scan returns no signals → no trade executed."""
        trade_mock = MagicMock()
        p = self._patches()
        with patch("bot.runner.scan_watchlist", return_value=[]), \
             p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_only_high_impact_headlines_sent_to_llm(self):
        """Only high-impact news headlines are passed to LLM."""
        provider = _mock_provider()
        low  = NewsItem(headline="Noise headline", score=1, high_impact=False)
        high = NewsItem(headline="NVDA acquisition", score=8, high_impact=True)
        p = self._patches(provider=provider)
        with p["scan"], \
             patch("bot.runner.classify_news", return_value=[low, high]), \
             p["llm"], p["risk"], p["trade"], p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        call_kwargs = provider.get_decision.call_args[1]
        assert call_kwargs["headlines"] == ["NVDA acquisition"]
        assert "Noise headline" not in call_kwargs["headlines"]

    def test_buy_allowed_in_neutral_with_high_confidence(self):
        """BUY en régime NEUTRAL avec confidence >= 0.75 → trade exécuté."""
        trade_mock = MagicMock(return_value=TradeResult("NVDA", True, "b1", "s1"))
        provider = _mock_provider(action=Action.BUY, confidence=0.80)
        p = self._patches(provider=provider, regime=_NEUTRAL)
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        trade_mock.assert_called_once()

    def test_buy_blocked_in_neutral_with_low_confidence(self):
        """BUY en régime NEUTRAL avec confidence < 0.75 → trade bloqué."""
        trade_mock = MagicMock()
        provider = _mock_provider(action=Action.BUY, confidence=0.70)
        p = self._patches(provider=provider, regime=_NEUTRAL)
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        trade_mock.assert_not_called()
