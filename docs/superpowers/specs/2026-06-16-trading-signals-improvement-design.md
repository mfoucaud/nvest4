# Design — Amélioration des signaux de trading

**Date :** 2026-06-16  
**Objectif :** Maximiser le P&L absolu en paper trading, 100% gratuit  
**Contexte :** Win rate actuel 25%, P&L -123$ sur trades fermés. Problème central : le bot achète des actifs défensifs en downtrend sans filtre de tendance marché.

---

## 1. Watchlist — Actifs momentum high-beta

**Remplacer** les mega-caps défensives (CVX, KO, WMT, JNJ, PEP, DIS, XOM, PG, BAC, JPM) par :

```python
WATCHLIST = [
    # Momentum high-beta
    "NVDA", "AMD", "SMCI", "PLTR", "COIN", "MSTR", "RDDT", "CRWD", "ANET", "UBER",
    # Restants de l'ancienne watchlist avec bon profil momentum
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "ADBE",
]
```

**Rationale :** Ces actifs ont une beta élevée, amplifient les mouvements du marché. Les signaux momentum sont plus fiables et le trailing stop adaptatif a davantage de sens que sur des défensives.

---

## 2. Filtre de tendance marché (Market Regime)

**Nouveau module : `bot/market_regime.py`**

Calculé une fois par cycle avant de scanner la watchlist.

| Condition | Régime | Actions autorisées |
|-----------|--------|-------------------|
| SPY > EMA50 > EMA200 | BULL | BUY uniquement |
| SPY < EMA50 < EMA200 | BEAR | SELL/SHORT uniquement |
| Sinon | NEUTRAL | BUY + SELL, seuil confiance 0.75 |

**Données utilisées :** yfinance SPY daily, EMA50, EMA200 (gratuit).

**Impact sur runner.py :**
- Le régime est passé à chaque décision LLM
- Côté `runner.py` : bloquer les décisions contradictoires (BUY en BEAR, SELL en BULL) indépendamment de ce que dit le LLM

---

## 3. Signaux techniques enrichis + confluence

**Modifications de `bot/scanner.py` :**

Nouveaux indicateurs (via `pandas_ta`, déjà installé) :
- **MACD** (12/26/9) — momentum directionnel, signal = croisement ligne MACD/signal
- **ADX** (14) — force de la tendance, valide uniquement si ADX > 25
- **ATR** (14) — volatilité pour le trailing stop adaptatif

**Règle de confluence :**
- Exiger **≥ 2 signaux** parmi : RSI oversold/overbought, EMA cross, MACD cross, volume spike
- ADX > 25 obligatoire pour valider le passage au LLM
- Un actif avec 1 seul signal est ignoré (actuellement le filtre accepte 1)

**Multi-timeframe :**
- Télécharger données **1h** (yfinance `interval="1h"`, `period="30d"`) en plus du daily
- Condition : EMA9 > EMA21 sur 1h pour un BUY (alignement direction)
- Si daily et 1h sont contradictoires → ignorer l'actif

**Trailing stop adaptatif :**
- Remplacer `trail_percent=5.0` fixe par `round(2 * atr / close * 100, 1)`
- Borné entre 3% et 10% pour éviter les extrêmes
- Exemple : NVDA ATR=8, prix=120 → trail = 2*8/120*100 = 13.3% → borné à 10%

---

## 4. Enrichissement du prompt LLM

**Ajouts au `PROMPT_TEMPLATE` dans `bot/llm.py` :**

```
Régime marché: {market_regime} (SPY EMA50/200)
SPY performance 5j: {spy_perf_5d:+.1f}%
Prix récents ({ticker}, 5 dernières bougies daily): {recent_prices}
Tendance 5j: {price_trend:+.1f}%
ATR(14): {atr:.2f} | Trail stop calculé: {trail_pct:.1f}%
```

**Seuil de confiance minimum :**
- Ajout dans le prompt : *"Ne réponds BUY ou SELL que si ta confidence >= 0.65. En régime NEUTRAL, le seuil est 0.75."*
- Filtre côté `runner.py` : rejeter `decision.confidence < 0.65` avant `validate_order`

**Signature `get_decision` mise à jour :**
```python
def get_decision(self, ticker, signals, headlines, open_positions, capital,
                 market_regime, spy_perf_5d, recent_prices, atr, trail_pct) -> LLMDecision
```

---

## 5. Fichiers modifiés

| Fichier | Nature de la modification |
|---------|--------------------------|
| `main.py` | Mise à jour watchlist |
| `bot/market_regime.py` | **Nouveau** — calcul SPY regime |
| `bot/scanner.py` | MACD, ADX, ATR, confluence ≥2, multi-timeframe 1h |
| `bot/llm.py` | Prompt enrichi, signature get_decision étendue |
| `bot/runner.py` | Appel market_regime, filtre confiance, trail adaptatif |

---

## 6. Ce qui ne change pas

- Architecture générale (scanner → LLM → risk → trader)
- `bot/risk.py` — gestion du capital (10% par position, MAX_POSITIONS=10)
- `bot/trader.py` — exécution Alpaca
- `bot/persistence.py` / `bot/dashboard.py`
- Stack 100% gratuite : yfinance, Groq/Gemini free tier, Alpaca paper

---

## 7. Résultats attendus

- Élimination des trades contraires à la tendance (problème CVX/KO/WMT en downtrend)
- Réduction du nombre de trades mais meilleure qualité (confluence ≥2 + ADX)
- Win rate cible : > 50%
- Trailing stop mieux calibré → laisser courir les winners, couper vite les losers
