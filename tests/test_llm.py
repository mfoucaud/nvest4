import json
import pytest
from unittest.mock import MagicMock, patch
from bot.llm import get_decision, LLMDecision, Action


def _mock_gemini(action="BUY", confidence=0.85, reasoning="Strong RSI signal"):
    response_json = json.dumps({
        "action":     action,
        "ticker":     "AAPL",
        "confidence": confidence,
        "reasoning":  reasoning,
    })
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value.text = response_json
    return mock_client


class TestGetDecision:
    def test_returns_buy_decision(self):
        with patch("bot.llm.genai.Client", return_value=_mock_gemini("BUY")):
            decision = get_decision(
                ticker="AAPL",
                signals=["RSI_OVERSOLD(30.0)"],
                headlines=["Apple beats earnings estimates"],
                open_positions=[],
                capital=10_000.0,
                api_key="fake-key",
            )
        assert decision.action == Action.BUY
        assert decision.ticker == "AAPL"

    def test_returns_hold_decision(self):
        with patch("bot.llm.genai.Client", return_value=_mock_gemini("HOLD")):
            decision = get_decision(
                ticker="MSFT", signals=["VOL_SPIKE(1.6x)"],
                headlines=[], open_positions=[], capital=10_000.0, api_key="fake-key",
            )
        assert decision.action == Action.HOLD

    def test_confidence_is_preserved(self):
        with patch("bot.llm.genai.Client", return_value=_mock_gemini(confidence=0.92)):
            decision = get_decision(
                ticker="AAPL", signals=[], headlines=[],
                open_positions=[], capital=10_000.0, api_key="fake-key",
            )
        assert decision.confidence == pytest.approx(0.92)

    def test_reasoning_is_preserved(self):
        with patch("bot.llm.genai.Client", return_value=_mock_gemini(reasoning="Volume spike on earnings day")):
            decision = get_decision(
                ticker="AAPL", signals=[], headlines=[],
                open_positions=[], capital=10_000.0, api_key="fake-key",
            )
        assert decision.reasoning == "Volume spike on earnings day"

    def test_returns_hold_on_malformed_response(self):
        mock_model = MagicMock()
        mock_model.generate_content.return_value.text = "not valid json"
        with patch("bot.llm.genai.Client", return_value=mock_model):
            decision = get_decision(
                ticker="AAPL", signals=[], headlines=[],
                open_positions=[], capital=10_000.0, api_key="fake-key",
            )
        assert decision.action == Action.HOLD
        assert "parse" in decision.reasoning.lower()

    def test_prompt_includes_ticker_and_signals(self):
        mock_model = _mock_gemini(action="BUY")
        with patch("bot.llm.genai.Client", return_value=mock_model):
            get_decision(
                ticker="NVDA", signals=["RSI_OVERBOUGHT(70.0)", "EMA_CROSS_DOWN"],
                headlines=[], open_positions=[], capital=10_000.0, api_key="fake-key",
            )
        prompt = mock_model.models.generate_content.call_args[1]["contents"]
        assert "NVDA" in prompt
        assert "RSI_OVERBOUGHT" in prompt
