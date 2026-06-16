# bot/llm.py
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


PROMPT_TEMPLATE = """\
Tu es un analyste financier spécialisé en trading directionnel. Analyse cet actif et retourne une décision JSON.

Ticker: {ticker}
Signaux techniques: {signals}
Headlines: {headlines}
Positions déjà ouvertes (à éviter): {open_positions}
Capital disponible: ${capital:.0f}

Contexte marché:
- Régime SPY: {market_regime} (BULL=uptrend EMA50>EMA200, BEAR=downtrend, NEUTRAL=indécis)
- SPY performance 5 derniers jours: {spy_perf_5d:+.1f}%
- Prix récents {ticker} (5 dernières bougies daily): {recent_prices}
- Tendance prix 5j: {price_trend:+.1f}%
- ATR(14): {atr:.2f} | Trailing stop calculé: {trail_pct:.1f}%

Définitions des actions :
- BUY  : ouvrir une position LONGUE (tu penses que le prix va MONTER)
- SELL : ouvrir une position COURTE / short (tu penses que le prix va BAISSER)
- HOLD : ne rien faire

Règles absolues :
- Ne réponds jamais BUY ou SELL si le ticker est déjà dans "positions déjà ouvertes".
- Ne réponds BUY ou SELL que si ta confidence >= 0.65.
- En régime NEUTRAL, le seuil de confidence est 0.75.
- En régime BULL, privilégie BUY. En régime BEAR, privilégie SELL.

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
        market_regime:  str,
        spy_perf_5d:    float,
        recent_prices:  list[float],
        atr:            float,
        trail_pct:      float,
    ) -> LLMDecision: ...


def get_llm_provider(config: dict) -> LLMProvider:
    provider = config.get("llm_provider", "groq").lower()
    if provider == "groq":
        api_key = config.get("groq_api_key")
        if not api_key:
            raise ValueError("Missing required config: groq_api_key")
        from bot.llm_groq import GroqProvider
        return GroqProvider(api_key=api_key)
    if provider == "gemini":
        api_key = config.get("gemini_api_key")
        if not api_key:
            raise ValueError("Missing required config: gemini_api_key")
        from bot.llm_gemini import GeminiProvider
        return GeminiProvider(api_key=api_key)
    raise ValueError(f"Unknown LLM provider: {provider}. Valid options: groq, gemini")
