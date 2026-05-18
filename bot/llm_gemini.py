# bot/llm_gemini.py
import json
import time

from google import genai
from google.genai.errors import ClientError

from bot.llm import PROMPT_TEMPLATE, LLMDecision, Action

MODEL = "gemini-2.0-flash"


class GeminiProvider:
    def __init__(self, api_key: str, model: str = MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def get_decision(
        self,
        ticker:         str,
        signals:        list[str],
        headlines:      list[str],
        open_positions: list[str],
        capital:        float,
    ) -> LLMDecision:
        prompt = PROMPT_TEMPLATE.format(
            ticker=ticker,
            signals=", ".join(signals) or "aucun",
            headlines="\n".join(f"- {h}" for h in headlines) or "aucune",
            open_positions=", ".join(open_positions) or "aucune",
            capital=capital,
        )

        for attempt in range(3):
            try:
                raw  = self.client.models.generate_content(model=self.model, contents=prompt).text
                data = json.loads(raw)
                return LLMDecision(
                    action=Action(data["action"]),
                    ticker=data["ticker"],
                    confidence=float(data["confidence"]),
                    reasoning=data["reasoning"],
                )
            except ClientError as e:
                err_str = str(e)
                is_daily_quota = "PerDay" in err_str or "per_day" in err_str.lower()
                if "429" in err_str and not is_daily_quota and attempt < 2:
                    wait = 15 * (attempt + 1)
                    print(f"[gemini] 429 rate limit {ticker}, retry in {wait}s (attempt {attempt+1})")
                    time.sleep(wait)
                    continue
                if is_daily_quota:
                    print(f"[gemini] daily quota exhausted for {ticker}, skipping retries")
                return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                                   reasoning=f"Gemini API error : {e}")
            except Exception as e:
                return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                                   reasoning=f"Impossible de parser la réponse Gemini : {e}")
        return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                           reasoning="Gemini max retries exceeded")
