# Design : Order History & Correlation Tool

**Date :** 2026-06-16  
**Scope :** Script standalone `tools/order_history.py`

---

## Objectif

Récupérer l'historique des ordres Alpaca sur une période donnée, corréler les BUY avec leurs SELL correspondants, calculer le PnL réel de chaque trade, et produire un rapport terminal + export CSV optionnel.

---

## Architecture

Script Python standalone. Aucune dépendance au runner ou au dashboard. Utilise directement le SDK Alpaca et lit `analyses.json` en option.

```
tools/
  order_history.py   ← script principal
```

---

## CLI

```
python tools/order_history.py --days 30 [--output trades.csv] [--analyses analyses.json]
```

Arguments :
- `--days N` (défaut : 30) — période d'historique à récupérer
- `--output FILE` — chemin CSV d'export (optionnel)
- `--analyses FILE` — chemin vers analyses.json pour enrichissement (optionnel)

Variables d'env requises : `ALPACA_KEY`, `ALPACA_SECRET` (ou `.env`)

---

## Données source

- `client.get_orders(status="all", after=<date>)` — tous les ordres sur la période
- `analyses.json` — optionnel, pour enrichir avec `stop_id` et `reasoning` LLM

---

## Corrélation BUY → SELL

1. Filtrer les ordres `filled` uniquement
2. Grouper par ticker
3. Pour chaque ticker, trier par date
4. Matcher chaque BUY avec le SELL `filled` suivant sur le même ticker
5. Type de clôture détecté :
   - `trailing_stop` si l'ordre SELL est de type `trailing_stop`
   - `manual` si market/limit SELL
   - `expired` si ordre expiré sans fill correspondant
6. Si `analyses.json` fourni : enrichir avec `reasoning` LLM via `buy_id`

---

## Calculs par trade

- `pnl` = `(exit_price - entry_price) × qty` (LONG) ou inverse (SHORT)
- `duration` = `filled_at(SELL) - filled_at(BUY)` en minutes
- `win` = pnl > 0

---

## Sorties

### Terminal

```
════════════════════════════════════════
  KPIs GLOBAUX
  Trades : 18  |  Win Rate : 61%  |  PnL Total : +$342.50
════════════════════════════════════════

TRADES
Ticker  Dir    Entrée   Sortie   Qté  PnL        Durée   Résultat  Clôture
AAPL    LONG   $182.40  $186.10   5   +$18.50    2h14m   WIN       trailing_stop
TSLA    LONG   $245.00  $238.20   3   -$20.40    45m     LOSS      trailing_stop
...

STATS PAR TICKER
Ticker  Trades  Win Rate  PnL Moyen  Durée Moy
AAPL       5      80%      +$14.20    1h32m
TSLA       3      33%       -$8.10    55m
...
```

Utilise `tabulate` pour les tableaux, couleurs via `colorama` (vert/rouge).

### CSV

Colonnes : `ticker, direction, entry_price, exit_price, qty, pnl, duration_min, win, close_type, entry_time, exit_time, reasoning`

---

## Dépendances

- `alpaca-py` (déjà présent)
- `tabulate`
- `colorama`
- `python-dotenv` (déjà présent probablement)

---

## Gestion d'erreurs

- Ordre BUY sans SELL correspondant → affiché comme "position ouverte ou orpheline", exclu des stats
- API Alpaca indisponible → message d'erreur clair et exit code 1
- `analyses.json` absent si `--analyses` spécifié → warning, continue sans enrichissement
