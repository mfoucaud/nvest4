# Post-Trade Review — Design Spec

**Date:** 2026-06-20  
**Status:** approved

---

## Objectif

Analyser rétrospectivement chaque trade fermé avec un LLM pour évaluer la pertinence du signal d'entrée, du timing et du sizing. Accumuler les leçons sur le Gist pour améliorer la stratégie au fil du temps.

---

## Architecture

### Nouveau module : `tools/trade_reviewer.py`

Responsabilité unique : pour une liste de trades fermés non-encore reviewés, fetcher les données enrichies et appeler le LLM pour produire un objet `TradeReview`.

Appelé depuis `main.py` après le cycle principal, avant le push vers le Gist.

### Persistance

Le schéma de `analyses.json` gagne une clé `reviews` : une liste d'objets `TradeReview` indexés par `(ticker, timestamp_entry)`. Les trades reviewés sont marqués `reviewed: true` dans la liste `trades` de leur run.

Structure persistée :
```json
{
  "reviews": [
    {
      "ticker": "NVDA",
      "direction": "LONG",
      "entry": 134.5,
      "exit": 141.2,
      "pnl": 67.0,
      "entry_ts": "2026-06-18 14:30",
      "exit_ts": "2026-06-19 10:15",
      "signal_score": 7,
      "timing_score": 5,
      "sizing_score": 8,
      "overall": 6,
      "verdict": "Signal solide mais entrée précipitée...",
      "lesson": "Attendre confirmation sur 2 bougies avant entrée en régime NEUTRAL."
    }
  ]
}
```

---

## Données collectées par trade

Pour chaque trade fermé non-reviewé, `trade_reviewer.py` collecte :

| Source | Données |
|--------|---------|
| `analyses.json` | direction, entry/exit price, qty, PnL, reasoning LLM d'origine |
| Alpaca historical data | OHLCV du jour d'entrée + jour de sortie (bougies 1h) |
| `market_regime.get_market_regime()` à la date d'entrée | régime SPY, perf SPY 5j |
| Alpaca news API | headlines du ticker dans la fenêtre ±1 jour autour de l'entrée |

Si une source est indisponible, le LLM reçoit ce qu'on a. Le `verdict` l'indique explicitement.

---

## Prompt LLM

Le LLM reçoit un prompt structuré contenant toutes les données ci-dessus et produit un JSON strict :

```json
{
  "signal_score": 7,
  "timing_score": 5,
  "sizing_score": 8,
  "overall": 6,
  "verdict": "...",
  "lesson": "..."
}
```

- **signal_score** (1-10) : pertinence des indicateurs techniques et news qui ont déclenché l'ordre
- **timing_score** (1-10) : qualité du moment d'entrée/sortie par rapport au mouvement réel
- **sizing_score** (1-10) : adéquation du sizing et calibration du stop
- **overall** (1-10) : note globale
- **verdict** : analyse narrative (~100 mots)
- **lesson** : règle actionnable pour la prochaine fois (~30 mots)

Le provider LLM utilisé est celui configuré dans `CONFIG` (Groq par défaut). Coût estimé ~2k tokens/trade.

---

## Limites & contraintes

- **Max 5 reviews par run** pour ne pas allonger le cycle principal.
- Un trade marqué `reviewed: true` n'est jamais ré-analysé.
- En cas d'erreur LLM ou de données insuffisantes, le trade reste `reviewed: false` et sera retentés au prochain run.
- Pas de tests unitaires (trop couplé aux APIs externes) — validation par run manuel.

---

## Dashboard

Nouvelle section dans le dashboard HTML existant (après les trades fermés) :

### 1. Tableau des reviews récentes
Une ligne par trade reviewé (30 derniers) :
- Ticker + direction badge
- Scores signal/timing/sizing sous forme de badges colorés (≥7 vert, 4-6 orange, <4 rouge)
- Score overall
- Verdict en ligne dépliable (click to expand)

### 2. Bloc "Leçons apprises"
Les `lesson` des 10 derniers trades reviewés, listées chronologiquement. C'est la section centrale pour l'amélioration de la stratégie.

### 3. Indicateurs de progression
Scores moyens signal/timing/sizing sur les 30 derniers trades reviewés — permet de visualiser si la stratégie progresse.

---

## Intégration dans `main.py`

```python
from tools.trade_reviewer import review_pending_trades

# Après run_cycle, avant push_to_gist
reviews = load_reviews_from_gist(gist_id, token)
new_reviews = review_pending_trades(
    closed_trades=closed_trades,
    existing_reviews=reviews,
    config=CONFIG,
    max_per_run=5,
)
reviews.extend(new_reviews)
# reviews inclus dans le payload push_to_gist
```

---

## Fichiers impactés

| Fichier | Modification |
|---------|-------------|
| `tools/trade_reviewer.py` | **nouveau** — logique review + fetch données enrichies |
| `bot/dashboard.py` | nouvelle section post-trade review dans `render_dashboard()` |
| `bot/persistence.py` | `load_reviews_from_gist` / `push_to_gist` étendu avec `reviews` |
| `main.py` | appel `review_pending_trades` + passage des reviews au dashboard |
