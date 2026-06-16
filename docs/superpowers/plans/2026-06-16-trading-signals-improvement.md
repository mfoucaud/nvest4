# Trading Signals Improvement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Améliorer le P&L du bot en ajoutant un filtre de tendance marché, des signaux techniques enrichis avec confluence obligatoire, un contexte LLM plus riche, et une watchlist momentum high-beta.

**Architecture:** Nouveau module `market_regime` calculé une fois par cycle → scanner enrichi avec MACD/ADX/ATR/confluence ≥2/trend 1h → prompt LLM enrichi avec contexte marché → runner filtrant confiance <0.65 et décisions contradictoires avec le régime.

**Tech Stack:** Python, pandas_ta (déjà installé), yfinance (déjà installé), pytest, unittest.mock

---

## File Map

| Fichier | Action | Responsabilité |
|---------|--------|----------------|
| `bot/market_regime.py` | **Créer** | Calcul du régime SPY (BULL/BEAR/NEUTRAL) + perf 5j |
| `bot/scanner.py` | **Modifier** | MACD, ADX, ATR, confluence ≥2, trend 1h |
| `bot/llm.py` | **Modifier** | Prompt enrichi, Protocol signature étendue |
| `bot/llm_groq.py` | **Modifier** | Nouveaux kwargs dans get_decision |
| `bot/llm_gemini.py` | **Modifier** | Nouveaux kwargs dans get_decision |
| `bot/runner.py` | **Modifier** | market_regime, filtre confiance, trail adaptatif, blocage contradictions |
| `main.py` | **Modifier** | Watchlist momentum high-beta |
| `tests/test_market_regime.py` | **Créer** | Tests du module market_regime |
| `tests/test_scanner.py` | **Modifier** | Tests nouveaux signaux et confluence |
| `tests/test_runner.py` | **Modifier** | Mocks mis à jour (nouveaux kwargs, market_regime) |

---

## Task 1: Module `bot/market_regime.py`

**Files:**
- Create: `bot/market_regime.py`
- Create: `tests/test_market_regime.py`

- [ ] **Step 1 : Écrire les tests**

```python
# tests/test_market_regime.py
import pandas as pd
import pytest
from unittest.mock import patch
from bot.market_regime import get_market_regime, MarketRegime


def _spy_df(closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.today(), periods=len(closes), freq="B")
    return pd.DataFrame({
        "Open": closes, "High": [c + 1 for c in closes],
        "Low": [c - 1 for c in closes], "Close": closes,
        "Volume": [1_000_000] * len(closes),
    }, index=dates)


def _bull_spy() -> pd.DataFrame:
    """Prix croissant sur 250 jours → EMA50 et EMA200 en uptrend, prix > EMA50 > EMA200."""
    closes = [100.0 + i * 0.5 for i in range(250)]
    return _spy_df(closes)


def _bear_spy() -> pd.DataFrame:
    """Prix décroissant sur 250 jours → prix < EMA50 < EMA200."""
    closes = [225.0 - i * 0.5 for i in range(250)]
    return _spy_df(closes)


def _neutral_spy() -> pd.DataFrame:
    """Prix oscillant → NEUTRAL."""
    import math
    closes = [150.0 + 10 * math.sin(i * 0.1) for i in range(250)]
    return _spy_df(closes)


class TestGetMarketRegime:
    def test_bull_market_detected(self):
        with patch("bot.market_regime.fetch_spy") as mock:
            mock.return_value = _bull_spy()
            result = get_market_regime()
        assert result.regime == "BULL"

    def test_bear_market_detected(self):
        with patch("bot.market_regime.fetch_spy") as mock:
            mock.return_value = _bear_spy()
            result = get_market_regime()
        assert result.regime == "BEAR"

    def test_returns_market_regime_dataclass(self):
        with patch("bot.market_regime.fetch_spy") as mock:
            mock.return_value = _bull_spy()
            result = get_market_regime()
        assert isinstance(result, MarketRegime)
        assert isinstance(result.spy_perf_5d, float)

    def test_spy_perf_5d_is_correct(self):
        closes = [100.0 + i * 0.5 for i in range(250)]
        df = _spy_df(closes)
        with patch("bot.market_regime.fetch_spy") as mock:
            mock.return_value = df
            result = get_market_regime()
        # perf 5j = (close[-1] - close[-6]) / close[-6] * 100
        expected = (closes[-1] - closes[-6]) / closes[-6] * 100
        assert result.spy_perf_5d == pytest.approx(expected, rel=1e-3)

    def test_fallback_neutral_when_fetch_fails(self):
        with patch("bot.market_regime.fetch_spy", return_value=None):
            result = get_market_regime()
        assert result.regime == "NEUTRAL"
        assert result.spy_perf_5d == 0.0
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
pytest tests/test_market_regime.py -v
```
Attendu : `ModuleNotFoundError: No module named 'bot.market_regime'`

- [ ] **Step 3 : Créer `bot/market_regime.py`**

```python
# bot/market_regime.py
from dataclasses import dataclass

import pandas as pd
import yfinance as yf


@dataclass
class MarketRegime:
    regime: str        # "BULL" | "BEAR" | "NEUTRAL"
    spy_perf_5d: float # performance SPY sur 5 jours en %


def fetch_spy() -> pd.DataFrame | None:
    df = yf.download("SPY", period="2y", interval="1d", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or len(df) < 210:
        return None
    return df


def get_market_regime() -> MarketRegime:
    df = fetch_spy()
    if df is None:
        print("[market_regime] SPY fetch failed, defaulting to NEUTRAL")
        return MarketRegime(regime="NEUTRAL", spy_perf_5d=0.0)

    close = df["Close"]
    ema50  = close.ewm(span=50,  adjust=False).mean().iloc[-1]
    ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
    price  = float(close.iloc[-1])

    if price > ema50 > ema200:
        regime = "BULL"
    elif price < ema50 < ema200:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"

    spy_perf_5d = float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100)

    print(f"[market_regime] {regime} | SPY={price:.2f} EMA50={ema50:.2f} EMA200={ema200:.2f} perf5j={spy_perf_5d:+.2f}%")
    return MarketRegime(regime=regime, spy_perf_5d=spy_perf_5d)
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
pytest tests/test_market_regime.py -v
```
Attendu : 5 PASSED

- [ ] **Step 5 : Commit**

```bash
git add bot/market_regime.py tests/test_market_regime.py
git commit -m "feat: add market regime module (SPY EMA50/200 BULL/BEAR/NEUTRAL)"
```

---

## Task 2: Scanner enrichi — MACD, ADX, ATR, confluence, trend 1h

**Files:**
- Modify: `bot/scanner.py`
- Modify: `tests/test_scanner.py`

- [ ] **Step 1 : Mettre à jour les tests du scanner**

Remplacer le contenu de `tests/test_scanner.py` par :

```python
import pandas as pd
import pytest
from unittest.mock import patch
from bot.scanner import compute_signals, scan_watchlist, SignalResult


# --- helpers ---------------------------------------------------------------

def _prices(values: list[float], volumes: list[int] | None = None) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.today(), periods=len(values), freq="B")
    vols = volumes if volumes else [2_000_000] * len(values)
    return pd.DataFrame({
        "Open":   values,
        "High":   [v + 0.5 for v in values],
        "Low":    [v - 0.5 for v in values],
        "Close":  values,
        "Volume": vols,
    }, index=dates)


def _declining(n=60, start=100.0, step=1.0) -> pd.DataFrame:
    """60 jours de baisse → RSI oversold + EMA cross DOWN."""
    return _prices([start - i * step for i in range(n)])


def _rising(n=60, start=50.0, step=1.0) -> pd.DataFrame:
    """60 jours de hausse → RSI overbought + EMA cross UP."""
    return _prices([start + i * step for i in range(n)])


def _flat(n=60, price=100.0) -> pd.DataFrame:
    return _prices([price] * n)


def _strong_trend_up(n=60) -> pd.DataFrame:
    """Tendance haussière forte : RSI overbought + EMA_CROSS_UP + VOL_SPIKE + ADX élevé."""
    closes = [50.0 + i * 1.5 for i in range(n)]
    volumes = [2_000_000] * n
    volumes[-1] = 7_000_000  # volume spike
    return _prices(closes, volumes)


def _1h_df(trend: str, n: int = 200) -> pd.DataFrame:
    """DataFrame 1h simulé avec tendance UP ou DOWN."""
    if trend == "UP":
        closes = [100.0 + i * 0.1 for i in range(n)]
    else:
        closes = [120.0 - i * 0.1 for i in range(n)]
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="h")
    return pd.DataFrame({
        "Open": closes, "High": [c + 0.1 for c in closes],
        "Low": [c - 0.1 for c in closes], "Close": closes,
        "Volume": [500_000] * n,
    }, index=dates)


# --- compute_signals -------------------------------------------------------

class TestComputeSignals:
    def test_result_has_atr_field(self):
        result = compute_signals(_rising(), "AAPL", _1h_df("UP"))
        assert isinstance(result.atr, float)
        assert result.atr > 0

    def test_flat_ticker_fails_confluence(self):
        """Un actif plat ne génère pas 2 signaux → passes_filter=False."""
        result = compute_signals(_flat(), "MSFT", _1h_df("UP"))
        assert not result.passes_filter

    def test_strong_trend_passes_confluence(self):
        """Tendance forte → ≥2 signaux + ADX>25 → passes_filter=True."""
        result = compute_signals(_strong_trend_up(), "NVDA", _1h_df("UP"))
        assert result.passes_filter
        assert len(result.signals) >= 2

    def test_1h_trend_included_in_signals(self):
        result = compute_signals(_rising(), "AAPL", _1h_df("UP"))
        assert any("TREND_1H" in s for s in result.signals)

    def test_result_carries_ticker_and_close(self):
        df = _flat(price=123.45)
        result = compute_signals(df, "KO", _1h_df("UP"))
        assert result.ticker == "KO"
        assert result.close == pytest.approx(123.45, rel=1e-3)

    def test_single_signal_not_enough(self):
        """Un seul signal (ex: volume spike seul sur actif flat) → passes_filter=False."""
        n = 60
        vols = [2_000_000] * n
        vols[-1] = 7_000_000
        df = _prices([100.0] * n, vols)
        result = compute_signals(df, "XOM", _1h_df("UP"))
        # RSI sera ~50 (flat), pas d'EMA cross, pas de MACD signal → 1 seul signal
        # Confluence exige ≥2 → False
        assert not result.passes_filter


# --- scan_watchlist --------------------------------------------------------

class TestScanWatchlist:
    def test_returns_only_tickers_with_signal(self):
        with patch("bot.scanner.fetch_ohlcv", side_effect=lambda t: _strong_trend_up() if t == "NVDA" else _flat()), \
             patch("bot.scanner.fetch_ohlcv_1h", return_value=_1h_df("UP")):
            results = scan_watchlist(["NVDA", "MSFT"])
        assert len(results) == 1
        assert results[0].ticker == "NVDA"

    def test_skips_ticker_when_fetch_returns_none(self):
        with patch("bot.scanner.fetch_ohlcv", return_value=None), \
             patch("bot.scanner.fetch_ohlcv_1h", return_value=None):
            results = scan_watchlist(["AAPL"])
        assert results == []
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
pytest tests/test_scanner.py -v
```
Attendu : plusieurs FAILED (champs `atr` manquant, signatures différentes)

- [ ] **Step 3 : Réécrire `bot/scanner.py`**

```python
# bot/scanner.py
from dataclasses import dataclass, field
import pandas as pd
import pandas_ta as ta
import yfinance as yf

RSI_OVERSOLD    = 35
RSI_OVERBOUGHT  = 65
VOLUME_SPIKE_MX = 1.5
LOOKBACK_DAYS   = 20
ADX_MIN         = 25     # force de tendance minimale
MIN_SIGNALS     = 2      # confluence obligatoire


@dataclass
class SignalResult:
    ticker:        str
    close:         float
    rsi:           float | None
    atr:           float
    signals:       list[str] = field(default_factory=list)
    passes_filter: bool = False


def fetch_ohlcv(ticker: str) -> pd.DataFrame | None:
    df = yf.download(ticker, period="60d", interval="1d", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or len(df) < 22:
        return None
    return df


def fetch_ohlcv_1h(ticker: str) -> pd.DataFrame | None:
    df = yf.download(ticker, period="30d", interval="1h", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or len(df) < 21:
        return None
    return df


def _trend_1h(df_1h: pd.DataFrame | None) -> str:
    """Retourne 'UP', 'DOWN' ou 'NEUTRAL' selon EMA9 vs EMA21 sur 1h."""
    if df_1h is None or len(df_1h) < 22:
        return "NEUTRAL"
    df = df_1h.copy()
    df.ta.ema(length=9,  append=True)
    df.ta.ema(length=21, append=True)
    latest = df.iloc[-1]
    ema9  = latest.get("EMA_9")
    ema21 = latest.get("EMA_21")
    if ema9 is None or ema21 is None:
        return "NEUTRAL"
    if ema9 > ema21:
        return "UP"
    if ema9 < ema21:
        return "DOWN"
    return "NEUTRAL"


def compute_signals(df: pd.DataFrame, ticker: str,
                    df_1h: pd.DataFrame | None = None) -> SignalResult:
    df = df.copy()
    df.ta.rsi(length=14, append=True)
    df.ta.ema(length=9,  append=True)
    df.ta.ema(length=21, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.adx(length=14, append=True)
    df.ta.atr(length=14, append=True)

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    rsi    = latest.get("RSI_14")
    ema9   = latest.get("EMA_9")
    ema21  = latest.get("EMA_21")
    p_ema9 = prev.get("EMA_9")
    p_ema21= prev.get("EMA_21")
    macd   = latest.get("MACD_12_26_9")
    macd_s = latest.get("MACDs_12_26_9")
    p_macd = prev.get("MACD_12_26_9")
    p_macd_s = prev.get("MACDs_12_26_9")
    adx    = latest.get("ADX_14")
    atr_val= latest.get("ATRr_14") or latest.get("ATR_14") or 0.0

    volume  = float(latest["Volume"])
    avg_vol = float(df["Volume"].iloc[-LOOKBACK_DAYS - 1:-1].mean())
    close   = float(latest["Close"])

    signals = []

    # RSI
    if rsi is not None:
        if rsi < RSI_OVERSOLD:
            signals.append(f"RSI_OVERSOLD({rsi:.1f})")
        elif rsi > RSI_OVERBOUGHT:
            signals.append(f"RSI_OVERBOUGHT({rsi:.1f})")

    # EMA cross
    if all(v is not None for v in [ema9, ema21, p_ema9, p_ema21]):
        if p_ema9 < p_ema21 and ema9 > ema21:
            signals.append("EMA_CROSS_UP")
        elif p_ema9 > p_ema21 and ema9 < ema21:
            signals.append("EMA_CROSS_DOWN")

    # MACD cross
    if all(v is not None for v in [macd, macd_s, p_macd, p_macd_s]):
        if p_macd < p_macd_s and macd > macd_s:
            signals.append("MACD_CROSS_UP")
        elif p_macd > p_macd_s and macd < macd_s:
            signals.append("MACD_CROSS_DOWN")

    # Volume spike
    if avg_vol > 0 and volume > avg_vol * VOLUME_SPIKE_MX:
        signals.append(f"VOL_SPIKE({volume / avg_vol:.1f}x)")

    # Trend 1h
    trend = _trend_1h(df_1h)
    if trend != "NEUTRAL":
        signals.append(f"TREND_1H_{trend}")

    # Confluence : ≥ MIN_SIGNALS et ADX suffisant
    adx_ok = adx is not None and float(adx) >= ADX_MIN
    passes = len(signals) >= MIN_SIGNALS and adx_ok

    return SignalResult(
        ticker=ticker,
        close=close,
        rsi=float(rsi) if rsi is not None else None,
        atr=float(atr_val),
        signals=signals,
        passes_filter=passes,
    )


def scan_watchlist(tickers: list[str]) -> list[SignalResult]:
    results = []
    for ticker in tickers:
        df = fetch_ohlcv(ticker)
        if df is None:
            continue
        df_1h = fetch_ohlcv_1h(ticker)
        result = compute_signals(df, ticker, df_1h)
        if result.passes_filter:
            results.append(result)
    return results
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
pytest tests/test_scanner.py -v
```
Attendu : tous les tests PASSED

- [ ] **Step 5 : Commit**

```bash
git add bot/scanner.py tests/test_scanner.py
git commit -m "feat: enrich scanner with MACD/ADX/ATR, confluence >=2, 1h trend"
```

---

## Task 3: Prompt LLM enrichi + signature étendue

**Files:**
- Modify: `bot/llm.py`
- Modify: `bot/llm_groq.py`
- Modify: `bot/llm_gemini.py`
- Modify: `tests/test_llm.py`

- [ ] **Step 1 : Lire les tests LLM existants**

```
cat tests/test_llm.py
```
(pour comprendre ce qui existe avant de modifier)

- [ ] **Step 2 : Mettre à jour `bot/llm.py`**

```python
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
```

- [ ] **Step 3 : Mettre à jour `bot/llm_groq.py`**

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
        market_regime:  str = "NEUTRAL",
        spy_perf_5d:    float = 0.0,
        recent_prices:  list[float] | None = None,
        atr:            float = 0.0,
        trail_pct:      float = 5.0,
    ) -> LLMDecision:
        recent_prices = recent_prices or []
        price_trend = 0.0
        if len(recent_prices) >= 2:
            price_trend = (recent_prices[-1] - recent_prices[0]) / recent_prices[0] * 100

        prompt = PROMPT_TEMPLATE.format(
            ticker=ticker,
            signals=", ".join(signals) or "aucun",
            headlines="\n".join(f"- {h}" for h in headlines) or "aucune",
            open_positions=", ".join(open_positions) or "aucune",
            capital=capital,
            market_regime=market_regime,
            spy_perf_5d=spy_perf_5d,
            recent_prices=[round(p, 2) for p in recent_prices],
            price_trend=price_trend,
            atr=atr,
            trail_pct=trail_pct,
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

- [ ] **Step 4 : Mettre à jour `bot/llm_gemini.py`**

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
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def get_decision(
        self,
        ticker:         str,
        signals:        list[str],
        headlines:      list[str],
        open_positions: list[str],
        capital:        float,
        market_regime:  str = "NEUTRAL",
        spy_perf_5d:    float = 0.0,
        recent_prices:  list[float] | None = None,
        atr:            float = 0.0,
        trail_pct:      float = 5.0,
    ) -> LLMDecision:
        recent_prices = recent_prices or []
        price_trend = 0.0
        if len(recent_prices) >= 2:
            price_trend = (recent_prices[-1] - recent_prices[0]) / recent_prices[0] * 100

        prompt = PROMPT_TEMPLATE.format(
            ticker=ticker,
            signals=", ".join(signals) or "aucun",
            headlines="\n".join(f"- {h}" for h in headlines) or "aucune",
            open_positions=", ".join(open_positions) or "aucune",
            capital=capital,
            market_regime=market_regime,
            spy_perf_5d=spy_perf_5d,
            recent_prices=[round(p, 2) for p in recent_prices],
            price_trend=price_trend,
            atr=atr,
            trail_pct=trail_pct,
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
```

- [ ] **Step 5 : Vérifier que les tests LLM existants passent encore**

```
pytest tests/test_llm.py -v
```
Attendu : tous PASSED (les nouveaux kwargs ont des valeurs par défaut)

- [ ] **Step 6 : Commit**

```bash
git add bot/llm.py bot/llm_groq.py bot/llm_gemini.py
git commit -m "feat: enrich LLM prompt with market regime, ATR, recent prices, confidence threshold"
```

---

## Task 4: Runner — market regime, filtre confiance, trail adaptatif, blocage contradictions

**Files:**
- Modify: `bot/runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1 : Mettre à jour les tests du runner**

Remplacer le contenu de `tests/test_runner.py` par :

```python
# tests/test_runner.py
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
            "scan":    patch("bot.runner.scan_watchlist",   return_value=[_signal()]),
            "news":    patch("bot.runner.classify_news",    return_value=_news_items(high_impact=True)),
            "llm":     patch("bot.runner.get_llm_provider", return_value=provider),
            "risk":    patch("bot.runner.validate_order",   return_value=_approved_order()),
            "trade":   patch("bot.runner.execute_order",    return_value=TradeResult("NVDA", True, "b1", "s1")),
            "account": patch("bot.runner.get_account"),
            "positions": patch("bot.runner.get_positions",  return_value=[]),
            "regime":  patch("bot.runner.get_market_regime", return_value=regime),
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
        """SELL en régime BULL → trade bloqué."""
        short_mock = MagicMock()
        provider = _mock_provider(action=Action.SELL)
        p = self._patches(provider=provider, regime=_BULL)
        with p["scan"], p["news"], p["llm"], p["risk"], \
             patch("bot.runner.execute_short_order", short_mock), p["account"], p["positions"], p["regime"]:
            run_cycle(watchlist=["NVDA"], config=_CONFIG)
        short_mock.assert_not_called()

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
```

Ajouter en tête du fichier l'import manquant :
```python
import pytest
```

- [ ] **Step 2 : Vérifier que les tests échouent**

```
pytest tests/test_runner.py -v
```
Attendu : FAILED sur `compute_trail_pct` (not found), `get_market_regime` (not patched), etc.

- [ ] **Step 3 : Réécrire `bot/runner.py`**

```python
# bot/runner.py
from dataclasses import dataclass, field

from alpaca.trading.client import TradingClient

from bot.scanner import scan_watchlist
from bot.news import classify_news
from bot.llm import get_llm_provider, Action
from bot.risk import validate_order
from bot.trader import execute_order, execute_short_order
from bot.market_regime import get_market_regime

CONFIDENCE_MIN         = 0.65
CONFIDENCE_MIN_NEUTRAL = 0.75


def compute_trail_pct(atr: float, close: float) -> float:
    """Trailing stop adaptatif : 2×ATR/prix, borné entre 3% et 10%."""
    if close <= 0 or atr <= 0:
        return 5.0
    pct = round(2 * atr / close * 100, 1)
    return max(3.0, min(10.0, pct))


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

    regime = get_market_regime()
    print(f"[runner] Market regime: {regime.regime} | SPY 5j: {regime.spy_perf_5d:+.1f}%")

    llm     = get_llm_provider(config)
    signals = scan_watchlist(watchlist)
    summary = RunSummary()

    for signal in signals:
        ticker = signal.ticker
        print(f"[runner] analysing {ticker}...")
        summary.analysed.append(ticker)

        news_items    = classify_news(ticker)
        headlines     = [n.headline for n in news_items if n.high_impact]
        trail_pct     = compute_trail_pct(signal.atr, signal.close)

        # 5 derniers prix de clôture (best-effort depuis signal)
        recent_prices: list[float] = [signal.close]  # fallback minimal

        decision = llm.get_decision(
            ticker=ticker,
            signals=signal.signals,
            headlines=headlines,
            open_positions=open_tickers,
            capital=capital,
            market_regime=regime.regime,
            spy_perf_5d=regime.spy_perf_5d,
            recent_prices=recent_prices,
            atr=signal.atr,
            trail_pct=trail_pct,
        )

        if decision.action == Action.HOLD:
            summary.skipped.append({"ticker": ticker, "reason": "HOLD",
                                     "reasoning": decision.reasoning})
            continue

        # Filtre confiance minimum
        min_conf = CONFIDENCE_MIN_NEUTRAL if regime.regime == "NEUTRAL" else CONFIDENCE_MIN
        if decision.confidence < min_conf:
            summary.skipped.append({
                "ticker": ticker,
                "reason": f"LOW_CONFIDENCE({decision.confidence:.2f}<{min_conf})",
                "reasoning": decision.reasoning,
            })
            continue

        # Blocage des décisions contradictoires avec le régime
        if regime.regime == "BULL" and decision.action == Action.SELL:
            summary.skipped.append({"ticker": ticker, "reason": "REGIME_CONFLICT(BULL+SELL)",
                                     "reasoning": decision.reasoning})
            continue
        if regime.regime == "BEAR" and decision.action == Action.BUY:
            summary.skipped.append({"ticker": ticker, "reason": "REGIME_CONFLICT(BEAR+BUY)",
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

        direction = decision.action.value
        try:
            if decision.action == Action.BUY:
                result = execute_order(alpaca, ticker=ticker, qty=order.qty,
                                       trail_percent=trail_pct)
            else:
                result = execute_short_order(alpaca, ticker=ticker, qty=order.qty,
                                             trail_percent=trail_pct)
        except (TimeoutError, RuntimeError) as e:
            print(f"[runner] {e}")
            summary.skipped.append({"ticker": ticker, "reason": "TIMEOUT", "reasoning": str(e)})
            continue

        summary.trades.append({
            "ticker":    ticker,
            "qty":       order.qty,
            "direction": direction,
            "buy_id":    result.buy_id,
            "stop_id":   result.stop_id,
            "reasoning": decision.reasoning,
        })
        open_tickers.append(ticker)

    return summary
```

- [ ] **Step 4 : Vérifier que les tests passent**

```
pytest tests/test_runner.py -v
```
Attendu : tous PASSED

- [ ] **Step 5 : Vérifier que tous les tests du projet passent**

```
pytest -v
```
Attendu : tous PASSED (0 failures)

- [ ] **Step 6 : Commit**

```bash
git add bot/runner.py tests/test_runner.py
git commit -m "feat: runner uses market regime, confidence filter, adaptive trail stop"
```

---

## Task 5: Watchlist momentum high-beta

**Files:**
- Modify: `main.py`

- [ ] **Step 1 : Mettre à jour la watchlist dans `main.py`**

Remplacer le bloc `WATCHLIST` :

```python
WATCHLIST = [
    # Momentum high-beta
    "NVDA", "AMD", "SMCI", "PLTR", "COIN", "MSTR", "RDDT", "CRWD", "ANET", "UBER",
    # Mega-caps momentum (conservés)
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "ADBE",
]
```

- [ ] **Step 2 : Vérifier que le projet démarre sans erreur**

```
python -c "from main import WATCHLIST, CONFIG; print(f'{len(WATCHLIST)} tickers configured')"
```
Attendu : `18 tickers configured`

- [ ] **Step 3 : Lancer une suite de tests complète finale**

```
pytest -v
```
Attendu : tous PASSED

- [ ] **Step 4 : Commit final**

```bash
git add main.py
git commit -m "feat: update watchlist to momentum high-beta tickers (NVDA, AMD, PLTR, COIN...)"
```
