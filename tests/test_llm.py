# tests/test_llm.py
import json
import pytest
from unittest.mock import MagicMock, patch
from bot.llm import LLMDecision, Action, get_llm_provider, LLMProvider
from bot.llm_gemini import GeminiProvider


def _mock_gemini_client(action="BUY", confidence=0.85, reasoning="Strong RSI signal", ticker="AAPL"):
    response_json = json.dumps({
        "action":     action,
        "ticker":     ticker,
        "confidence": confidence,
        "reasoning":  reasoning,
    })
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value.text = response_json
    return mock_client


class TestGeminiProvider:
    def test_returns_buy_decision(self):
        with patch("bot.llm_gemini.genai.Client", return_value=_mock_gemini_client("BUY")):
            provider = GeminiProvider(api_key="fake-key")
            decision = provider.get_decision(
                ticker="AAPL",
                signals=["RSI_OVERSOLD(30.0)"],
                headlines=["Apple beats earnings estimates"],
                open_positions=[],
                capital=10_000.0,
            )
        assert decision.action == Action.BUY
        assert decision.ticker == "AAPL"

    def test_returns_hold_decision(self):
        with patch("bot.llm_gemini.genai.Client", return_value=_mock_gemini_client("HOLD", ticker="MSFT")):
            provider = GeminiProvider(api_key="fake-key")
            decision = provider.get_decision(
                ticker="MSFT", signals=["VOL_SPIKE(1.6x)"],
                headlines=[], open_positions=[], capital=10_000.0,
            )
        assert decision.action == Action.HOLD

    def test_confidence_is_preserved(self):
        with patch("bot.llm_gemini.genai.Client", return_value=_mock_gemini_client(confidence=0.92)):
            provider = GeminiProvider(api_key="fake-key")
            decision = provider.get_decision(
                ticker="AAPL", signals=[], headlines=[],
                open_positions=[], capital=10_000.0,
            )
        assert decision.confidence == pytest.approx(0.92)

    def test_reasoning_is_preserved(self):
        with patch("bot.llm_gemini.genai.Client", return_value=_mock_gemini_client(reasoning="Volume spike on earnings day")):
            provider = GeminiProvider(api_key="fake-key")
            decision = provider.get_decision(
                ticker="AAPL", signals=[], headlines=[],
                open_positions=[], capital=10_000.0,
            )
        assert decision.reasoning == "Volume spike on earnings day"

    def test_returns_hold_on_malformed_response(self):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value.text = "not valid json"
        with patch("bot.llm_gemini.genai.Client", return_value=mock_client):
            provider = GeminiProvider(api_key="fake-key")
            decision = provider.get_decision(
                ticker="AAPL", signals=[], headlines=[],
                open_positions=[], capital=10_000.0,
            )
        assert decision.action == Action.HOLD
        assert "parse" in decision.reasoning.lower()

    def test_prompt_includes_ticker_and_signals(self):
        mock_client = _mock_gemini_client(action="BUY")
        with patch("bot.llm_gemini.genai.Client", return_value=mock_client):
            provider = GeminiProvider(api_key="fake-key")
            provider.get_decision(
                ticker="NVDA", signals=["RSI_OVERBOUGHT(70.0)", "EMA_CROSS_DOWN"],
                headlines=[], open_positions=[], capital=10_000.0,
            )
        prompt = mock_client.models.generate_content.call_args[1]["contents"]
        assert "NVDA" in prompt
        assert "RSI_OVERBOUGHT" in prompt


class TestFactory:
    def test_groq_provider_returned_for_groq(self):
        from bot.llm_groq import GroqProvider
        with patch("bot.llm_groq.Groq"):
            provider = get_llm_provider({"llm_provider": "groq", "groq_api_key": "k"})
        assert isinstance(provider, GroqProvider)

    def test_gemini_provider_returned_for_gemini(self):
        with patch("bot.llm_gemini.genai.Client"):
            provider = get_llm_provider({"llm_provider": "gemini", "gemini_api_key": "k"})
        assert isinstance(provider, GeminiProvider)

    def test_factory_raises_on_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_provider({"llm_provider": "openai", "groq_api_key": "k"})

    def test_provider_satisfies_protocol(self):
        with patch("bot.llm_gemini.genai.Client"):
            provider = get_llm_provider({"llm_provider": "gemini", "gemini_api_key": "k"})
        assert isinstance(provider, LLMProvider)
