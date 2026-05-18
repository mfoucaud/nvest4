# LLM Provider Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `LLMProvider` abstraction so the bot can switch between Groq and Gemini via env var, defaulting to Groq (generous free tier).

**Architecture:** A `Protocol` in `bot/llm.py` defines the provider interface. A factory `get_llm_provider(config)` returns the correct provider instance. Each provider (`GeminiProvider`, `GroqProvider`) lives in its own file and implements `get_decision(...)`.

**Tech Stack:** Python 3.11+, `groq` package (OpenAI-compatible SDK), `google-genai` (existing), `pytest` for tests.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `bot/llm.py` | Modify | Protocol, shared types (`LLMDecision`, `Action`), `PROMPT_TEMPLATE`, factory |
| `bot/llm_gemini.py` | Create | `GeminiProvider` class (existing logic moved) |
| `bot/llm_groq.py` | Create | `GroqProvider` class (new) |
| `bot/runner.py` | Modify | Use factory instead of `get_decision`, filter `high_impact` headlines |
| `main.py` | Modify | New config keys: `llm_provider`, `groq_api_key`, `gemini_api_key` |
| `requirements.txt` | Modify | Add `groq` |
| `tests/test_llm.py` | Modify | Test `GeminiProvider` and `GroqProvider` directly + factory |
| `tests/test_runner.py` | Modify | Mock `get_llm_provider` instead of `get_decision` |

---

## Task 1: Refactor bot/llm.py — Protocol, factory, shared types

**Files:**
- Modify: `bot/llm.py`

- [ ] **Step 1: Replace bot/llm.py with the new structure**

```python
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
```

- [ ] **Step 2: Verify the file is valid Python**

```bash
python -c "from bot.llm import LLMProvider, LLMDecision, Action, get_llm_provider; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add bot/llm.py
git commit -m "refactor: extract Protocol, factory and shared types in bot/llm.py"
```

---

## Task 2: Create bot/llm_gemini.py — move existing Gemini logic

**Files:**
- Create: `bot/llm_gemini.py`
- Modify: `tests/test_llm.py`

- [ ] **Step 1: Write the failing test for GeminiProvider**

Replace the content of `tests/test_llm.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail (GeminiProvider not yet created)**

```bash
cd "C:/Users/micka/Desktop/project/!nvest4" && python -m pytest tests/test_llm.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` on `bot.llm_gemini`

- [ ] **Step 3: Create bot/llm_gemini.py**

```python
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
```

- [ ] **Step 4: Run tests to verify GeminiProvider and factory tests pass**

```bash
cd "C:/Users/micka/Desktop/project/!nvest4" && python -m pytest tests/test_llm.py::TestGeminiProvider tests/test_llm.py::TestFactory -v
```

Expected: All `TestGeminiProvider` tests pass. `TestFactory::test_groq_*` may fail (GroqProvider not yet created) — that's OK.

- [ ] **Step 5: Commit**

```bash
git add bot/llm_gemini.py tests/test_llm.py
git commit -m "feat: extract GeminiProvider into bot/llm_gemini.py, update tests"
```

---

## Task 3: Create bot/llm_groq.py — new Groq provider

**Files:**
- Create: `bot/llm_groq.py`

- [ ] **Step 1: Run the existing Groq factory test to confirm it fails**

```bash
cd "C:/Users/micka/Desktop/project/!nvest4" && python -m pytest tests/test_llm.py::TestFactory::test_groq_provider_returned_for_groq -v
```

Expected: FAIL with `ImportError` on `bot.llm_groq`

- [ ] **Step 2: Create bot/llm_groq.py**

```python
# bot/llm_groq.py
import json
import time

from groq import Groq

from bot.llm import PROMPT_TEMPLATE, LLMDecision, Action

MODEL = "llama-3.1-8b-instant"


class GroqProvider:
    def __init__(self, api_key: str, model: str = MODEL):
        self.client = Groq(api_key=api_key)
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
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw  = response.choices[0].message.content
                data = json.loads(raw)
                return LLMDecision(
                    action=Action(data["action"]),
                    ticker=data["ticker"],
                    confidence=float(data["confidence"]),
                    reasoning=data["reasoning"],
                )
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    wait = 15 * (attempt + 1)
                    print(f"[groq] 429 rate limit {ticker}, retry in {wait}s (attempt {attempt+1})")
                    time.sleep(wait)
                    continue
                return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                                   reasoning=f"Impossible de parser la réponse Groq : {e}")
        return LLMDecision(action=Action.HOLD, ticker=ticker, confidence=0.0,
                           reasoning="Groq max retries exceeded")
```

- [ ] **Step 3: Add GroqProvider tests to tests/test_llm.py**

Add this class at the end of `tests/test_llm.py`:

```python
class TestGroqProvider:
    def _mock_groq_client(self, action="BUY", confidence=0.85, reasoning="Strong signal", ticker="AAPL"):
        response_json = json.dumps({
            "action":     action,
            "ticker":     ticker,
            "confidence": confidence,
            "reasoning":  reasoning,
        })
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices[0].message.content = response_json
        return mock_client

    def test_returns_buy_decision(self):
        from bot.llm_groq import GroqProvider
        mock_client = self._mock_groq_client("BUY")
        with patch("bot.llm_groq.Groq", return_value=mock_client):
            provider = GroqProvider(api_key="fake-key")
            decision = provider.get_decision(
                ticker="AAPL", signals=["RSI_OVERSOLD(30.0)"],
                headlines=["Apple beats estimates"], open_positions=[], capital=10_000.0,
            )
        assert decision.action == Action.BUY
        assert decision.ticker == "AAPL"

    def test_returns_hold_on_malformed_response(self):
        from bot.llm_groq import GroqProvider
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices[0].message.content = "not json"
        with patch("bot.llm_groq.Groq", return_value=mock_client):
            provider = GroqProvider(api_key="fake-key")
            decision = provider.get_decision(
                ticker="AAPL", signals=[], headlines=[], open_positions=[], capital=10_000.0,
            )
        assert decision.action == Action.HOLD

    def test_prompt_includes_ticker_and_signals(self):
        from bot.llm_groq import GroqProvider
        mock_client = self._mock_groq_client(action="BUY")
        with patch("bot.llm_groq.Groq", return_value=mock_client):
            provider = GroqProvider(api_key="fake-key")
            provider.get_decision(
                ticker="NVDA", signals=["EMA_CROSS_UP"],
                headlines=[], open_positions=[], capital=10_000.0,
            )
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        prompt = call_kwargs["messages"][0]["content"]
        assert "NVDA" in prompt
        assert "EMA_CROSS_UP" in prompt

    def test_satisfies_llm_provider_protocol(self):
        from bot.llm_groq import GroqProvider
        with patch("bot.llm_groq.Groq"):
            provider = GroqProvider(api_key="fake-key")
        assert isinstance(provider, LLMProvider)
```

- [ ] **Step 4: Run all llm tests**

```bash
cd "C:/Users/micka/Desktop/project/!nvest4" && python -m pytest tests/test_llm.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add bot/llm_groq.py tests/test_llm.py
git commit -m "feat: add GroqProvider (llama-3.1-8b-instant) + tests"
```

---

## Task 4: Update bot/runner.py — use factory + filter high_impact headlines

**Files:**
- Modify: `bot/runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Update tests/test_runner.py to mock get_llm_provider**

Replace the content of `tests/test_runner.py`:

```python
# tests/test_runner.py
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


def _mock_provider(action=Action.BUY, ticker="AAPL"):
    provider = MagicMock()
    provider.get_decision.return_value = LLMDecision(
        action=action, ticker=ticker, confidence=0.85, reasoning="Strong signal"
    )
    return provider


def _approved_order(ticker="AAPL"):
    return OrderRequest(ticker=ticker, approved=True, qty=5, stop_price=142.5)


def _rejected_order(ticker="AAPL", reason=RejectionReason.MAX_POSITIONS_REACHED):
    return OrderRequest(ticker=ticker, approved=False, rejection=reason)


_CONFIG = {"llm_provider": "groq", "groq_api_key": "k", "alpaca_key": "a", "alpaca_secret": "s"}


class TestRunCycle:
    def _patches(self, provider=None):
        if provider is None:
            provider = _mock_provider()
        return {
            "scan":     patch("bot.runner.scan_watchlist",    return_value=[_signal()]),
            "news":     patch("bot.runner.classify_news",     return_value=_news_items(high_impact=True)),
            "llm":      patch("bot.runner.get_llm_provider",  return_value=provider),
            "risk":     patch("bot.runner.validate_order",    return_value=_approved_order()),
            "trade":    patch("bot.runner.execute_order",     return_value=TradeResult("AAPL", True, "b1", "s1")),
            "account":  patch("bot.runner.get_account"),
            "positions":patch("bot.runner.get_positions",     return_value=[]),
        }

    def test_returns_run_summary(self):
        p = self._patches()
        with p["scan"], p["news"], p["llm"], p["risk"], p["trade"], p["account"], p["positions"]:
            summary = run_cycle(watchlist=["AAPL"], config=_CONFIG)
        assert isinstance(summary, RunSummary)

    def test_trade_executed_on_buy_decision(self):
        trade_mock = MagicMock(return_value=TradeResult("AAPL", True, "b1", "s1"))
        p = self._patches()
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        trade_mock.assert_called_once()

    def test_no_trade_when_llm_says_hold(self):
        trade_mock = MagicMock()
        p = self._patches(provider=_mock_provider(action=Action.HOLD))
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_no_trade_when_risk_rejected(self):
        trade_mock = MagicMock()
        p = self._patches()
        with p["scan"], p["news"], p["llm"], \
             patch("bot.runner.validate_order", return_value=_rejected_order()), \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_summary_records_analysed_tickers(self):
        p = self._patches()
        with p["scan"], p["news"], p["llm"], p["risk"], p["trade"], p["account"], p["positions"]:
            summary = run_cycle(watchlist=["AAPL"], config=_CONFIG)
        assert "AAPL" in summary.analysed

    def test_no_trade_when_no_signal(self):
        trade_mock = MagicMock()
        p = self._patches()
        with patch("bot.runner.scan_watchlist", return_value=[]), \
             p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_order", trade_mock), p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        trade_mock.assert_not_called()

    def test_only_high_impact_headlines_sent_to_llm(self):
        provider = _mock_provider()
        low  = NewsItem(headline="Noise headline", score=1, high_impact=False)
        high = NewsItem(headline="Apple acquisition", score=8, high_impact=True)
        p = self._patches(provider=provider)
        with p["scan"], \
             patch("bot.runner.classify_news", return_value=[low, high]), \
             p["llm"], p["risk"], p["trade"], p["account"], p["positions"]:
            run_cycle(watchlist=["AAPL"], config=_CONFIG)
        call_kwargs = provider.get_decision.call_args[1]
        assert call_kwargs["headlines"] == ["Apple acquisition"]
        assert "Noise headline" not in call_kwargs["headlines"]
```

- [ ] **Step 2: Run tests to verify they fail (runner not yet updated)**

```bash
cd "C:/Users/micka/Desktop/project/!nvest4" && python -m pytest tests/test_runner.py -v 2>&1 | head -30
```

Expected: FAIL — `get_llm_provider` not yet imported in runner.

- [ ] **Step 3: Update bot/runner.py**

```python
# bot/runner.py
from dataclasses import dataclass, field

from alpaca.trading.client import TradingClient

from bot.scanner import scan_watchlist
from bot.news import classify_news
from bot.llm import get_llm_provider, Action
from bot.risk import validate_order
from bot.trader import execute_order


def get_account(client):
    return client.get_account()


def get_positions(client):
    return client.get_all_positions()


@dataclass
class RunSummary:
    analysed: list[str]  = field(default_factory=list)
    trades:   list[dict] = field(default_factory=list)
    skipped:  list[dict] = field(default_factory=list)


def run_cycle(watchlist: list[str], config: dict) -> RunSummary:
    alpaca       = TradingClient(config["alpaca_key"], config["alpaca_secret"], paper=True)
    account      = get_account(alpaca)
    positions    = get_positions(alpaca)
    open_tickers = [p.symbol for p in positions]
    capital      = float(account.cash)

    llm     = get_llm_provider(config)
    signals = scan_watchlist(watchlist)
    summary = RunSummary()

    for signal in signals:
        ticker = signal.ticker
        print(f"[runner] analysing {ticker}...")
        summary.analysed.append(ticker)

        news_items = classify_news(ticker)
        headlines  = [n.headline for n in news_items if n.high_impact]

        decision = llm.get_decision(
            ticker=ticker,
            signals=signal.signals,
            headlines=headlines,
            open_positions=open_tickers,
            capital=capital,
        )

        if decision.action != Action.BUY:
            summary.skipped.append({"ticker": ticker, "reason": decision.action.value,
                                     "reasoning": decision.reasoning})
            continue

        order = validate_order(
            ticker=ticker,
            price=signal.close,
            capital=capital,
            open_positions=open_tickers,
        )

        if not order.approved:
            summary.skipped.append({"ticker": ticker, "reason": order.rejection.value})
            continue

        result = execute_order(alpaca, ticker=ticker, qty=order.qty, trail_percent=5.0)
        summary.trades.append({
            "ticker":    ticker,
            "qty":       order.qty,
            "buy_id":    result.buy_id,
            "stop_id":   result.stop_id,
            "reasoning": decision.reasoning,
        })
        open_tickers.append(ticker)

    return summary
```

- [ ] **Step 4: Run runner tests**

```bash
cd "C:/Users/micka/Desktop/project/!nvest4" && python -m pytest tests/test_runner.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Run full test suite**

```bash
cd "C:/Users/micka/Desktop/project/!nvest4" && python -m pytest -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add bot/runner.py tests/test_runner.py
git commit -m "feat: use LLM factory in runner, filter high_impact headlines"
```

---

## Task 5: Update main.py + requirements.txt

**Files:**
- Modify: `main.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add groq to requirements.txt**

Replace `requirements.txt` content:

```
alpaca-py
yfinance
pandas-ta
google-genai
groq
requests
python-dotenv
pytest
```

- [ ] **Step 2: Install groq package**

```bash
pip install groq
```

Expected: `Successfully installed groq-x.x.x`

- [ ] **Step 3: Update CONFIG in main.py**

Replace the `CONFIG` block (lines 18-22):

```python
CONFIG = {
    "llm_provider":  os.environ.get("LLM_PROVIDER", "groq"),
    "groq_api_key":  os.environ.get("GROQ_API_KEY", ""),
    "gemini_api_key": os.environ.get("GOOGLEAI_STUDIO_API_KEY", ""),
    "alpaca_key":    os.environ["ALPACA_API_KEY"],
    "alpaca_secret": os.environ["ALPACA_API_SECRET"],
}
```

- [ ] **Step 4: Run full test suite**

```bash
cd "C:/Users/micka/Desktop/project/!nvest4" && python -m pytest -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add main.py requirements.txt
git commit -m "feat: add GROQ_API_KEY + LLM_PROVIDER config, add groq to requirements"
```

---

## Task 6: Add GROQ_API_KEY secret to GitHub Actions

**Files:**
- Read: `.github/workflows/*.yml` to find the workflow file

- [ ] **Step 1: Add GROQ_API_KEY to the workflow env block**

Find the workflow file (likely `.github/workflows/bot.yml` or similar). In the `env:` section of the job that runs the bot, add:

```yaml
GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
```

`LLM_PROVIDER` defaults to `groq` — no change needed unless you want to override.

- [ ] **Step 2: Add the secret in GitHub**

Go to: **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**
- Name: `GROQ_API_KEY`
- Value: your Groq API key from [console.groq.com](https://console.groq.com)

- [ ] **Step 3: Commit the workflow change**

```bash
git add .github/workflows/
git commit -m "ci: add GROQ_API_KEY env var to workflow"
```

---

## Verification

After all tasks are complete, run:

```bash
cd "C:/Users/micka/Desktop/project/!nvest4" && python -m pytest -v
```

Expected: All tests pass, no import errors. Switching provider: set `LLM_PROVIDER=gemini` + `GOOGLEAI_STUDIO_API_KEY=<key>` to fall back to Gemini with no code changes.
