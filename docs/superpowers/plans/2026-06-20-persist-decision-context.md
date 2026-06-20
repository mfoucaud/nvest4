# Persist Decision Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persister dans `analyses.json` les données de marché qui ont motivé chaque ordre (prix récents, signaux, ATR, régime, headlines), et les réutiliser dans la review post-trade à la place du re-fetch yfinance.

**Architecture:** `runner.py` enrichit le dict de chaque trade avec le contexte de décision au moment de l'ordre. `trade_reviewer.py` lit ces champs s'ils sont présents et les utilise dans `_fetch_enriched`, avec fallback yfinance pour les trades antérieurs sans ces données.

**Tech Stack:** Python 3.12, dataclasses (déjà en place)

---

## File Map

| Fichier | Action | Responsabilité |
|---------|--------|----------------|
| `bot/runner.py` | Modifier | Ajouter les champs de contexte dans `summary.trades.append()` |
| `tests/test_runner.py` | Modifier | Ajouter test qui vérifie la présence des nouveaux champs |
| `tools/trade_reviewer.py` | Modifier | `_fetch_enriched` utilise les données stockées si disponibles |

---

## Task 1: `bot/runner.py` — enrichir le dict de trade

**Files:**
- Modify: `bot/runner.py:138-145`
- Test: `tests/test_runner.py`

Le bloc `summary.trades.append({...})` à la ligne 138 ne stocke que `ticker`, `qty`, `direction`, `buy_id`, `stop_id`, `reasoning`. Il faut y ajouter les données de contexte disponibles à ce moment du code : `recent_prices`, `signals`, `atr`, `trail_pct`, `market_regime`, `spy_perf_5d`, `headlines`.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `tests/test_runner.py`, ajouter cette méthode dans la classe `TestRunCycle` :

```python
def test_trade_dict_contains_decision_context(self):
    """Trade dict persiste les données qui ont motivé la décision."""
    p = self._patches(regime=_BULL)
    with p["scan"], p["news"], p["llm"], p["risk"], p["trade"], p["account"], p["positions"], p["regime"]:
        summary = run_cycle(watchlist=["NVDA"], config=_CONFIG)
    assert len(summary.trades) == 1
    trade = summary.trades[0]
    assert "recent_prices" in trade
    assert "signals" in trade
    assert "atr" in trade
    assert "trail_pct" in trade
    assert "market_regime" in trade
    assert "spy_perf_5d" in trade
    assert "headlines" in trade
```

- [ ] **Step 2: Vérifier que le test échoue**

```bash
pytest tests/test_runner.py::TestRunCycle::test_trade_dict_contains_decision_context -v
```

Résultat attendu : `FAILED` — `AssertionError: assert 'recent_prices' in {...}`

- [ ] **Step 3: Modifier `runner.py` — enrichir summary.trades.append**

Remplacer le bloc `summary.trades.append({...})` (lignes 138-145) :

```python
        summary.trades.append({
            "ticker":        ticker,
            "qty":           order.qty,
            "direction":     direction,
            "buy_id":        result.buy_id,
            "stop_id":       result.stop_id,
            "reasoning":     decision.reasoning,
            "recent_prices": recent_prices,
            "signals":       signal.signals,
            "atr":           signal.atr,
            "trail_pct":     trail_pct,
            "market_regime": regime.regime,
            "spy_perf_5d":   regime.spy_perf_5d,
            "headlines":     headlines,
        })
```

- [ ] **Step 4: Vérifier que le test passe**

```bash
pytest tests/test_runner.py::TestRunCycle::test_trade_dict_contains_decision_context -v
```

Résultat attendu : `PASSED`

- [ ] **Step 5: Vérifier que tous les tests passent**

```bash
pytest tests/test_runner.py -v
```

Résultat attendu : tous `PASSED`

- [ ] **Step 6: Commit**

```bash
git add bot/runner.py tests/test_runner.py
git commit -m "feat: runner — persist decision context in trade dict (prices, signals, atr, regime)"
```

---

## Task 2: `tools/trade_reviewer.py` — utiliser les données stockées

**Files:**
- Modify: `tools/trade_reviewer.py` — fonction `_fetch_enriched`

Actuellement `_fetch_enriched` re-fetche toujours via yfinance. Si le trade dict contient les données de contexte stockées par le runner (Task 1), on les utilise directement — c'est plus rapide, plus fidèle (données exactes au moment de la décision), et évite des appels API inutiles. Fallback vers yfinance pour les trades antérieurs sans ces champs.

- [ ] **Step 1: Lire `tools/trade_reviewer.py`**

Lire le fichier pour comprendre la structure actuelle de `_fetch_enriched` avant de le modifier.

- [ ] **Step 2: Modifier `_fetch_enriched` pour utiliser les données stockées**

Remplacer le contenu de `_fetch_enriched` par :

```python
def _fetch_enriched(trade: dict) -> dict:
    """Fetche les données enrichies pour un trade.
    
    Priorité aux données stockées au moment de la décision (runner).
    Fallback vers yfinance pour les trades antérieurs.
    """
    ticker   = trade["ticker"]
    entry_ts = trade.get("timestamp", "")

    try:
        entry_dt = datetime.strptime(entry_ts, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        entry_dt = datetime.now(timezone.utc)

    # ── Prix intraday ────────────────────────────────────────────────────────
    stored_prices = trade.get("recent_prices")
    if stored_prices:
        lines = [f"  close={p:.2f}" for p in stored_prices]
        intraday_prices = "Prix journaliers au moment de la décision :\n" + "\n".join(lines)
    else:
        intraday_prices = "indisponible"
        try:
            start = (entry_dt - timedelta(days=1)).strftime("%Y-%m-%d")
            end   = (entry_dt + timedelta(days=2)).strftime("%Y-%m-%d")
            df = yf.download(ticker, start=start, end=end, interval="1h",
                             progress=False, auto_adjust=True)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                rows = df[["Open", "High", "Low", "Close"]].tail(12).round(2)
                lines = [f"  {idx.strftime('%m-%d %H:%M')} O={r['Open']} H={r['High']} L={r['Low']} C={r['Close']}"
                         for idx, r in rows.iterrows()]
                intraday_prices = "\n".join(lines)
        except Exception:
            pass

    # ── SPY context ──────────────────────────────────────────────────────────
    stored_regime    = trade.get("market_regime")
    stored_spy_perf  = trade.get("spy_perf_5d")
    if stored_regime is not None and stored_spy_perf is not None:
        spy_perf_5d = float(stored_spy_perf)
        spy_entry   = 0.0
    else:
        spy_perf_5d = 0.0
        spy_entry   = 0.0
        try:
            spy_start = (entry_dt - timedelta(days=8)).strftime("%Y-%m-%d")
            spy_end   = (entry_dt + timedelta(days=2)).strftime("%Y-%m-%d")
            spy_df = yf.download("SPY", start=spy_start, end=spy_end, interval="1d",
                                  progress=False, auto_adjust=True)
            if not spy_df.empty:
                if isinstance(spy_df.columns, pd.MultiIndex):
                    spy_df.columns = spy_df.columns.get_level_values(0)
                close = spy_df["Close"]
                spy_entry   = float(close.iloc[-1])
                spy_perf_5d = float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100) if len(close) >= 6 else 0.0
        except Exception:
            pass

    # ── News / headlines ─────────────────────────────────────────────────────
    stored_headlines = trade.get("headlines")
    if stored_headlines is not None:
        headlines = stored_headlines[:5]
    else:
        headlines = []
        try:
            news_items = classify_news(ticker)
            headlines  = [n.headline for n in news_items if n.high_impact][:5]
        except Exception:
            pass

    return {
        "intraday_prices": intraday_prices,
        "spy_perf_5d":     spy_perf_5d,
        "spy_entry":       spy_entry,
        "headlines":       headlines,
    }
```

Note : ce code importe `pandas as pd` pour `isinstance(df.columns, pd.MultiIndex)`. Vérifier si `pd` est déjà importé dans le fichier — si non, ajouter `import pandas as pd` en tête de fichier.

- [ ] **Step 3: Vérifier la syntaxe**

```bash
python -c "import tools.trade_reviewer; print('OK')"
```

Résultat attendu : `OK`

- [ ] **Step 4: Commit**

```bash
git add tools/trade_reviewer.py
git commit -m "feat: trade_reviewer — use stored decision context when available, fallback to yfinance"
```
