# bot/llm.py
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


PROMPT_TEMPLATE = """\
Tu es un analyste financier. Analyse cet actif et retourne une décision JSON.

Ticker: {ticker}
Signaux techniques: {signals}
Headlines: {headlines}
Positions ouvertes: {open_positions}
Capital disponible: ${capital:.0f}

Réponds UNIQUEMENT avec ce JSON (pas de markdown, pas d'explication) :
{{"action": "BUY"|"SELL"|"HOLD", "ticker": "{ticker}", "confidence": 0.0-1.0, "reasoning": "..."}}
"""


class Action(Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class LLMDecision:
    action:     Action
    ticker:     str
    confidence: float
    reasoning:  str


@runtime_checkable
class LLMProvider(Protocol):
    def get_decision(
        self,
        ticker:         str,
        signals:        list[str],
        headlines:      list[str],
        open_positions: list[str],
        capital:        float,
    ) -> LLMDecision: ...


def get_llm_provider(config: dict) -> LLMProvider:
    provider = config.get("llm_provider", "groq")
    if provider == "groq":
        from bot.llm_groq import GroqProvider
        return GroqProvider(api_key=config["groq_api_key"])
    if provider == "gemini":
        from bot.llm_gemini import GeminiProvider
        return GeminiProvider(api_key=config["gemini_api_key"])
    raise ValueError(f"Unknown LLM provider: {provider}")
