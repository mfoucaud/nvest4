# !nvest4 — Backlog

## Bloquant / À régler en premier

- [ ] **Quota Gemini épuisé** — activer la facturation sur Google AI Studio (pay-as-you-go, ~quelques centimes/mois pour ce volume). Sans ça le bot tourne mais ne génère que des HOLD.

## Bugs connus

- [ ] **Marché fermé (jours fériés US)** — le cron ne tient pas compte des jours fériés, le bot se lance et soumet des ordres qui ne se remplissent jamais. Fix : ajouter `alpaca.get_clock().is_open` dans `main.py` et sortir proprement si le marché est fermé.



- [ ] **Timeout GitHub Actions** — à surveiller au prochain run avec les logs de trace ajoutés (`[runner] analysing TICKER...`). Si ça retombe, investiguer yfinance ou le backoff Gemini.

## Améliorations prévues (phase 2)

- [ ] **Outil de supervision** — analyser les résultats historiques (`analyses.json`) pour ajuster les seuils RSI/volume (RSI_OVERSOLD=35, RSI_OVERBOUGHT=65, VOLUME_SPIKE_MX=1.5). Décidé en session : on gère ça séparément.
- [ ] **Sleep entre tickers** — ajouter 4-5s entre chaque appel Gemini dans `runner.py` pour rester sous les 15 RPM et éviter les 429.
- [ ] **Dashboard** — lien permanent via htmlpreview : `https://htmlpreview.github.io/?https://gist.githubusercontent.com/mfoucaud/3de561fe07fd6f8023838d1b3a576c33/raw/dashboard.html`
- [ ] **Win rate** — calculé à 0.0 en dur dans `main.py` (ligne 60), à implémenter dans l'outil de supervision.

## Infrastructure

- [ ] Vérifier que le Gist est bien mis à jour à chaque run (dashboard + analyses.json) une fois le quota Gemini réactivé.
