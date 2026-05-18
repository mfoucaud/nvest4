# LLM Provider Abstraction — Design Spec

**Date:** 2026-05-18  
**Status:** Approved

## Context

The bot currently uses Gemini 2.0 Flash (free tier) via `bot/llm.py`. The free tier quota is exhausted during normal operation (20 tickers × multiple daily runs). The goal is to:

1. Migrate the default provider to Groq (generous free tier)
2. Introduce an abstraction layer to switch providers via config without code changes
3. Fix an existing waste: all news headlines are sent to the LLM regardless of impact, inflating token usage ~3-4x unnecessarily

## Architecture

### File Structure

```
bot/
  llm.py          # Protocol LLMProvider, shared types (LLMDecision, Action), factory get_llm_provider()
  llm_gemini.py   # GeminiProvider — existing logic moved here
  llm_groq.py     # GroqProvider — new, uses openai-compatible SDK
  runner.py       # Minor fix: filter headlines to high_impact only
main.py           # Reads LLM_PROVIDER env var, passes to config
requirements.txt  # Add groq package
```

### Protocol

```python
# bot/llm.py
from typing import Protocol

class LLMProvider(Protocol):
    def get_decision(
        self,
        ticker: str,
        signals: list[str],
        headlines: list[str],
        open_positions: list[str],
        capital: float,
    ) -> LLMDecision: ...
```

`LLMDecision` and `Action` stay in `llm.py` as shared types.

### Factory

```python
# bot/llm.py
def get_llm_provider(config: dict) -> LLMProvider:
    provider = config.get("llm_provider", "groq")
    if provider == "groq":
        from bot.llm_groq import GroqProvider
        return GroqProvider(api_key=config["groq_api_key"])
    elif provider == "gemini":
        from bot.llm_gemini import GeminiProvider
        return GeminiProvider(api_key=config["gemini_api_key"])
    raise ValueError(f"Unknown LLM provider: {provider}")
```

### GroqProvider

Uses the `groq` package (OpenAI-compatible). Model: `llama-3.1-8b-instant` (default, configurable via `LLM_MODEL` env var). Same retry logic on 429 as current Gemini implementation.

### GeminiProvider

Existing `get_decision()` function logic moved into a class. No behavioral change.

### runner.py fix

```python
# Before
headlines = [n.headline for n in news_items]

# After
headlines = [n.headline for n in news_items if n.high_impact]
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_PROVIDER` | No | `groq` | `groq` or `gemini` |
| `GROQ_API_KEY` | If `LLM_PROVIDER=groq` | — | Groq API key |
| `GOOGLEAI_STUDIO_API_KEY` | If `LLM_PROVIDER=gemini` | — | Gemini API key |
| `LLM_MODEL` | No | provider default | Override model name |

### main.py config dict

```python
CONFIG = {
    "llm_provider":  os.environ.get("LLM_PROVIDER", "groq"),
    "groq_api_key":  os.environ.get("GROQ_API_KEY", ""),
    "gemini_api_key": os.environ.get("GOOGLEAI_STUDIO_API_KEY", ""),
    ...
}
```

### GitHub Actions

Add `GROQ_API_KEY` secret. `LLM_PROVIDER` defaults to `groq`, no change needed unless overriding.

## Data Flow

```
runner.py
  → get_llm_provider(config)          # factory returns GroqProvider or GeminiProvider
  → provider.get_decision(ticker, …)  # uniform interface
  → LLMDecision                       # same return type regardless of provider
```

## Error Handling

- 429 rate limit: retry up to 3 times with exponential backoff (15s, 30s) — same as current
- Parse error / API error: return `LLMDecision(action=HOLD, confidence=0.0)`
- Unknown provider in factory: raise `ValueError` at startup (fail fast)

## Testing

- Existing tests mock `get_decision()` at the runner level — no changes needed
- Add unit tests for the factory: assert correct provider class returned per config
- Add unit test for `high_impact` filter in runner

## Out of Scope

- Adding OpenAI, Anthropic, or other providers (can be added later via the same pattern)
- Model benchmarking / A/B testing
- Dynamic provider switching at runtime
