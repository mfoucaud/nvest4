# bot/llm_gemini.py
import json
import time

from google import genai
from google.genai.errors import ClientError

from bot.llm import PROMPT_TEMPLATE, LLMDecision, Action

MODEL = "gemini-2.0-flash"


class GeminiProvider:
    def __init__(self, api_key: str, model: str = MODEL):
        self.api_key = api_key
        self.model = model

    def get_decision(
        self,
        ticker:         str,
        signals:        list[str],
        headlines:      list[str],
        open_positions: list[str],
        capital:        float,
    ) -> LLMDecision:
        client = genai.Client(api_key=self.api_key)
        prompt = PROMPT_TEMPLATE.format(
            ticker=ticker,
            signals=", ".join(signals) or "aucun",
            headlines="\n".join(f"- {h}" for h in headlines) or "aucune",
            open_positions=", ".join(open_positions) or "aucune",
            capital=capital,
        )

        for attempt in range(3):
            try:
                raw  = client.models.generate_content(model=self.model, contents=prompt).text
                data = json.loads(raw)
                return LLMDecision(
                    action=Action(data["action"]),
                    ticker=data["ticker"],
                    confidence=float(data["confidence"]),
                    reasoning=data["reasoning"],
                )
            except ClientError as e:
                if "429" in str(e) and attempt < 2:
                    wait = 15 * (attempt + 1)
                    print(f"[gemini] 429 rate limit {ticker}, retry in {wait}s (attempt {attempt+1})")
                    time.sleep(wait)
                    continue
                return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                                   reasoning=f"Gemini API error : {e}")
            except Exception as e:
                return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                                   reasoning=f"Impossible de parser la réponse Gemini : {e}")
        return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                           reasoning="Gemini max retries exceeded")
