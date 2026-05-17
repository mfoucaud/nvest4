import json
import time
from dataclasses import dataclass
from enum import Enum

from google import genai
from google.genai.errors import ClientError

MODEL = "gemini-2.0-flash"

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


def get_decision(
    ticker:         str,
    signals:        list[str],
    headlines:      list[str],
    open_positions: list[str],
    capital:        float,
    api_key:        str,
) -> LLMDecision:
    client = genai.Client(api_key=api_key)

    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker,
        signals=", ".join(signals) or "aucun",
        headlines="\n".join(f"- {h}" for h in headlines) or "aucune",
        open_positions=", ".join(open_positions) or "aucune",
        capital=capital,
    )

    for attempt in range(3):
        try:
            raw  = client.models.generate_content(model=MODEL, contents=prompt).text
            data = json.loads(raw)
            return LLMDecision(
                action=Action(data["action"]),
                ticker=data["ticker"],
                confidence=float(data["confidence"]),
                reasoning=data["reasoning"],
            )
        except ClientError as e:
            if "429" in str(e) and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                               reasoning=f"Gemini API error : {e}")
        except Exception as e:
            return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                               reasoning=f"Impossible de parser la réponse Gemini : {e}")
