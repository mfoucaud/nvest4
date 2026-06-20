# Trade Detail View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une vue détail dépliable sur chaque trade clôturé dans le dashboard, affichant le contexte de décision (signaux, régime, ATR, prix récents, headlines) et la review LLM (scores, verdict, leçon).

**Architecture:** `main.py` étend les dicts de `closed_trades` avec les données de contexte (depuis `analyses.json`) et la review associée (depuis `all_reviews`), matchées par ticker. `bot/dashboard.py` rend chaque ligne comme un `<tr>` cliquable suivi d'un `<tr>` de détail masqué par défaut, révélé par un toggle JS inline.

**Tech Stack:** Python 3.12, HTML/CSS/JS inline (dashboard statique, pas de framework)

---

## File Map

| Fichier | Action | Responsabilité |
|---------|--------|----------------|
| `main.py` | Modifier | Construire `context_map` et `reviews_map` par ticker, les injecter dans `_pair_trades` |
| `bot/dashboard.py` | Modifier | Rows cliquables + panneau détail dépliable avec sections Décision et Review |

---

## Task 1: `main.py` — enrichir closed_trades avec contexte et review

**Files:**
- Modify: `main.py`

### Contexte

Actuellement `reasoning_map` (ligne ~70) est le seul enrichissement injecté dans `closed_trades`. On ajoute deux nouvelles maps keyed par ticker (last occurrence wins — limitation connue et acceptée) :

- `context_map` : `signals`, `atr`, `trail_pct`, `market_regime`, `spy_perf_5d`, `recent_prices`, `headlines`
- `reviews_map` : la review LLM complète (signal_score, timing_score, sizing_score, overall, verdict, lesson) pour ce ticker

Ces données sont injectées dans chaque dict de `closed_trades` via `_pair_trades`.

- [ ] **Step 1: Remplacer le bloc `reasoning_map` par un bloc `context_map` étendu**

Localiser ce bloc dans `main.py` (lignes ~69-73) :
```python
    # Reasoning map from analyses (best-effort enrichment)
    reasoning_map: dict[str, str] = {}
    for run in analyses:
        for trade in run.get("trades", []):
            reasoning_map[trade["ticker"]] = trade.get("reasoning", "")
```

Le remplacer par :
```python
    # Context map — best-effort enrichment par ticker (dernière occurrence)
    context_map: dict[str, dict] = {}
    for run in analyses:
        for trade in run.get("trades", []):
            context_map[trade["ticker"]] = {
                "reasoning":     trade.get("reasoning", ""),
                "signals":       trade.get("signals", []),
                "atr":           trade.get("atr", 0.0),
                "trail_pct":     trade.get("trail_pct", 0.0),
                "market_regime": trade.get("market_regime", ""),
                "spy_perf_5d":   trade.get("spy_perf_5d", 0.0),
                "recent_prices": trade.get("recent_prices", []),
                "headlines":     trade.get("headlines", []),
            }

    # Reviews map — dernière review par ticker
    reviews_map: dict[str, dict] = {}
    for r in all_reviews:
        reviews_map[r["ticker"]] = r
```

- [ ] **Step 2: Mettre à jour les deux usages de `reasoning_map` dans `main.py`**

**Usage 1** — `positions_data` (ligne ~150) :
```python
            "reasoning":  reasoning_map.get(p.symbol, ""),
```
Remplacer par :
```python
            "reasoning":  context_map.get(p.symbol, {}).get("reasoning", ""),
```

**Usage 2** — dans `_pair_trades` (ligne ~183) :
```python
                "reasoning": reasoning_map.get(ticker, ""),
```
Remplacer par :
```python
                "reasoning":     ctx.get("reasoning", ""),
                "signals":       ctx.get("signals", []),
                "atr":           ctx.get("atr", 0.0),
                "trail_pct":     ctx.get("trail_pct", 0.0),
                "market_regime": ctx.get("market_regime", ""),
                "spy_perf_5d":   ctx.get("spy_perf_5d", 0.0),
                "recent_prices": ctx.get("recent_prices", []),
                "headlines":     ctx.get("headlines", []),
                "review":        reviews_map.get(ticker),
```

Et au début du bloc `for entry in entries:` dans `_pair_trades`, ajouter la résolution de `ctx` :
```python
            ctx = context_map.get(ticker, {})
```

Note : `_pair_trades` est une closure définie à l'intérieur de `main()`, donc `context_map` et `reviews_map` sont accessibles par fermeture.

- [ ] **Step 3: Vérifier la syntaxe**

```bash
python -c "import main; print('OK')"
```

Résultat attendu : `OK`

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: main — inject decision context and review into closed_trades dicts"
```

---

## Task 2: `bot/dashboard.py` — lignes cliquables avec panneau détail

**Files:**
- Modify: `bot/dashboard.py`

### Contexte

La section "Trades Clôturés" dans `render_dashboard` génère des `<tr>` dans `closed_rows`. On transforme chaque ligne en deux `<tr>` :
1. La ligne existante, rendue cliquable (`cursor: pointer`, `onclick`)
2. Une nouvelle ligne cachée (`.detail-row`) contenant le panneau avec deux blocs : Décision + Review

Le toggle JS est minimal et inline dans le `<script>` du HTML.

- [ ] **Step 1: Ajouter le CSS `.detail-row` et `.detail-panel` dans le bloc `<style>`**

Dans `render_dashboard`, dans le bloc `<style>` du `return f"""..."""`, ajouter après la règle `.badge.short-badge{{ ... }}` :

```css
  .detail-row {{ display:none; }}
  .detail-row td {{ padding:0; border-bottom:1px solid #21262d; }}
  .detail-panel {{ background:#161b22; padding:16px 20px; display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .detail-section {{ }}
  .detail-section h4 {{ color:#58a6ff; font-size:.8em; text-transform:uppercase; letter-spacing:.4px; margin-bottom:8px; }}
  .detail-item {{ margin-bottom:6px; font-size:.82em; color:#8b949e; }}
  .detail-item strong {{ color:#e6edf3; }}
  .clickable-row {{ cursor:pointer; }}
  .clickable-row:hover td {{ background:#1c2128; }}
```

- [ ] **Step 2: Ajouter le `<script>` de toggle dans le HTML**

Juste avant la balise `</body>` dans le `return f"""..."""`, ajouter :

```html
<script>
function toggleDetail(id) {
  var row = document.getElementById(id);
  row.style.display = row.style.display === 'table-row' ? 'none' : 'table-row';
}
</script>
```

- [ ] **Step 3: Ajouter le helper `_render_trade_detail`**

Ajouter cette fonction juste avant `render_dashboard` :

```python
def _render_trade_detail(c: dict) -> str:
    """Génère le HTML du panneau de détail pour un trade clôturé."""
    # ── Bloc Décision ────────────────────────────────────────────────────────
    regime    = c.get("market_regime", "")
    spy_perf  = c.get("spy_perf_5d", 0.0)
    atr       = c.get("atr", 0.0)
    trail_pct = c.get("trail_pct", 0.0)
    signals   = c.get("signals", [])
    headlines = c.get("headlines", [])
    prices    = c.get("recent_prices", [])

    regime_color = {"BULL": "#3fb950", "BEAR": "#f85149", "NEUTRAL": "#d29922"}.get(regime, "#8b949e")

    signals_html = "".join(f'<span class="badge exp" style="margin:1px 2px;font-size:.72em">{s}</span>' for s in signals) or "—"
    headlines_html = "".join(f'<div style="margin:2px 0">• {h[:80]}{"…" if len(h)>80 else ""}</div>' for h in headlines[:3]) or "—"
    prices_str = " → ".join(f"{p:.2f}" for p in prices[-5:]) if prices else "—"

    decision_block = f"""
<div class="detail-section">
  <h4>Contexte de décision</h4>
  <div class="detail-item">Régime : <strong style="color:{regime_color}">{regime or "—"}</strong> (SPY 5j : {spy_perf:+.1f}%)</div>
  <div class="detail-item">ATR : <strong>{atr:.2f}</strong> | Trailing stop : <strong>{trail_pct:.1f}%</strong></div>
  <div class="detail-item">Signaux : {signals_html}</div>
  <div class="detail-item" style="margin-top:6px">Prix récents : <strong style="font-family:monospace">{prices_str}</strong></div>
  <div class="detail-item" style="margin-top:6px">Headlines :<br>{headlines_html}</div>
</div>"""

    # ── Bloc Review ──────────────────────────────────────────────────────────
    review = c.get("review")
    if review:
        verdict = review.get("verdict", "")
        lesson  = review.get("lesson", "")
        review_block = f"""
<div class="detail-section">
  <h4>Review LLM</h4>
  <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap">
    <span>Signal : {_score_badge(review.get("signal_score", 0))}</span>
    <span>Timing : {_score_badge(review.get("timing_score", 0))}</span>
    <span>Sizing : {_score_badge(review.get("sizing_score", 0))}</span>
    <span>Global : {_score_badge(review.get("overall", 0))}</span>
  </div>
  <div class="detail-item">{verdict}</div>
  <div class="detail-item" style="margin-top:8px;padding:8px;background:#0d1117;border-radius:6px;color:#d29922">
    <strong>Leçon :</strong> {lesson}
  </div>
</div>"""
    else:
        review_block = """
<div class="detail-section">
  <h4>Review LLM</h4>
  <div class="detail-item" style="color:#8b949e;font-style:italic">Pas encore analysé</div>
</div>"""

    return f'<div class="detail-panel">{decision_block}{review_block}</div>'
```

- [ ] **Step 4: Modifier la boucle `closed_rows` pour utiliser `_render_trade_detail`**

Dans la boucle `for c in closed_trades:` dans `render_dashboard`, remplacer le bloc qui construit `closed_rows` :

```python
        closed_rows += f"""
<tr>
  <td>{c.get("timestamp", "")}</td>
  <td><strong>{c["ticker"]}</strong> {dir_badge}</td>
  <td>{entry_str}</td>
  <td>{exit_str}</td>
  <td>{c.get("qty", "—")}</td>
  <td>{pnl_str}</td>
  <td>{badge}</td>
  <td style="color:#8b949e;font-size:.82em;max-width:260px">{expl}</td>
</tr>"""
```

Par :

```python
        detail_id = f"detail-{c['ticker']}-{c.get('timestamp','').replace(' ','-').replace(':','')}"
        detail_html = _render_trade_detail(c)
        closed_rows += f"""
<tr class="clickable-row" onclick="toggleDetail('{detail_id}')">
  <td>{c.get("timestamp", "")}</td>
  <td><strong>{c["ticker"]}</strong> {dir_badge}</td>
  <td>{entry_str}</td>
  <td>{exit_str}</td>
  <td>{c.get("qty", "—")}</td>
  <td>{pnl_str}</td>
  <td>{badge}</td>
  <td style="color:#8b949e;font-size:.82em;max-width:260px">{expl}</td>
</tr>
<tr class="detail-row" id="{detail_id}">
  <td colspan="8">{detail_html}</td>
</tr>"""
```

- [ ] **Step 5: Vérifier la syntaxe**

```bash
python -c "from bot.dashboard import render_dashboard; print('OK')"
```

Résultat attendu : `OK`

- [ ] **Step 6: Commit**

```bash
git add bot/dashboard.py
git commit -m "feat: dashboard — expandable trade detail rows with decision context and LLM review"
```
