# Post-Trade Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyser rétrospectivement chaque trade fermé avec un LLM (Groq) et afficher les scores/leçons dans une nouvelle section du dashboard existant.

**Architecture:** Un nouveau module `tools/trade_reviewer.py` fetche des données enrichies (OHLCV yfinance, news yfinance, SPY context) et appelle Groq pour produire un objet `TradeReview`. Les reviews sont persistées sur le Gist dans `reviews.json`. Le dashboard reçoit un paramètre `reviews` supplémentaire et rend une nouvelle section.

**Tech Stack:** Python 3.12, yfinance (déjà présent), Groq SDK (déjà présent), Alpaca SDK (déjà présent)

---

## File Map

| Fichier | Action | Responsabilité |
|---------|--------|----------------|
| `tools/trade_reviewer.py` | Créer | `TradeReview` dataclass, fetch données enrichies, appel LLM Groq, `review_pending_trades()` |
| `bot/persistence.py` | Modifier | `load_reviews_from_gist()`, `push_reviews_to_gist()` — `reviews.json` comme fichier séparé sur le Gist |
| `bot/dashboard.py` | Modifier | Ajouter param `reviews` à `render_dashboard()`, rendre 3 sous-sections |
| `main.py` | Modifier | Appeler `review_pending_trades()` + `load/push reviews` + passer reviews au dashboard |

---

## Task 1: `tools/trade_reviewer.py` — module core

**Files:**
- Create: `tools/trade_reviewer.py`

Ce module est autonome. Il ne dépend que de `bot.news.classify_news` et du SDK Groq.

- [ ] **Step 1: Créer le fichier avec `TradeReview` et le prompt**

```python
# tools/trade_reviewer.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import yfinance as yf
from groq import Groq

from bot.news import classify_news

GROQ_MODEL = "llama-3.1-8b-instant"

REVIEW_PROMPT = """\
Tu es un analyste financier expert. Évalue ce trade a posteriori et retourne un JSON strict.

=== TRADE ===
Ticker: {ticker}
Direction: {direction}
Entrée: ${entry:.2f} le {entry_ts}
Sortie: ${exit_:.2f} le {exit_ts}
Quantité: {qty} actions
PnL réalisé: {pnl_str}
Raisonnement LLM d'origine: {reasoning}

=== CONTEXTE MARCHÉ AU MOMENT DU TRADE ===
SPY performance 5j autour de l'entrée: {spy_perf_5d:+.1f}%
Prix SPY à l'entrée: ${spy_entry:.2f}

=== PRIX INTRADAY {ticker} (bougies 1h autour de l'entrée) ===
{intraday_prices}

=== NEWS RÉCENTES {ticker} ===
{headlines}

=== ÉVALUATION DEMANDÉE ===
- signal_score (1-10): Les signaux techniques et news justifiaient-ils l'entrée ?
- timing_score (1-10): L'entrée/sortie était-elle bien timée par rapport au mouvement réel ?
- sizing_score (1-10): Le sizing et le stop trailing étaient-ils bien calibrés ?
- overall (1-10): Note globale du trade
- verdict: Analyse narrative (~100 mots) — ce qui s'est passé, pourquoi ça a marché ou échoué
- lesson: UNE règle actionnable pour les prochains trades (~30 mots)

Réponds UNIQUEMENT avec ce JSON (pas de markdown, pas d'explication) :
{{"signal_score": 0, "timing_score": 0, "sizing_score": 0, "overall": 0, "verdict": "...", "lesson": "..."}}
"""


@dataclass
class TradeReview:
    ticker:       str
    direction:    str
    entry:        float
    exit_:        float
    pnl:          float | None
    entry_ts:     str
    exit_ts:      str
    signal_score: int
    timing_score: int
    sizing_score: int
    overall:      int
    verdict:      str
    lesson:       str

    def to_dict(self) -> dict:
        return {
            "ticker":       self.ticker,
            "direction":    self.direction,
            "entry":        self.entry,
            "exit":         self.exit_,
            "pnl":          self.pnl,
            "entry_ts":     self.entry_ts,
            "exit_ts":      self.exit_ts,
            "signal_score": self.signal_score,
            "timing_score": self.timing_score,
            "sizing_score": self.sizing_score,
            "overall":      self.overall,
            "verdict":      self.verdict,
            "lesson":       self.lesson,
        }
```

- [ ] **Step 2: Ajouter `_fetch_enriched`**

```python
def _fetch_enriched(trade: dict) -> dict:
    """Fetche OHLCV intraday, news et contexte SPY pour un trade."""
    ticker   = trade["ticker"]
    entry_ts = trade.get("timestamp", "")

    try:
        entry_dt = datetime.strptime(entry_ts, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        entry_dt = datetime.now(timezone.utc)

    start = (entry_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    end   = (entry_dt + timedelta(days=2)).strftime("%Y-%m-%d")

    # Prix intraday ticker
    intraday_prices = "indisponible"
    try:
        df = yf.download(ticker, start=start, end=end, interval="1h",
                         progress=False, auto_adjust=True)
        if not df.empty:
            if hasattr(df.columns, "get_level_values"):
                df.columns = df.columns.get_level_values(0)
            rows = df[["Open", "High", "Low", "Close"]].tail(12).round(2)
            lines = [f"  {idx.strftime('%m-%d %H:%M')} O={r['Open']} H={r['High']} L={r['Low']} C={r['Close']}"
                     for idx, r in rows.iterrows()]
            intraday_prices = "\n".join(lines)
    except Exception:
        pass

    # SPY context
    spy_perf_5d = 0.0
    spy_entry   = 0.0
    try:
        spy_start = (entry_dt - timedelta(days=8)).strftime("%Y-%m-%d")
        spy_df = yf.download("SPY", start=spy_start, end=end, interval="1d",
                              progress=False, auto_adjust=True)
        if not spy_df.empty:
            if hasattr(spy_df.columns, "get_level_values"):
                spy_df.columns = spy_df.columns.get_level_values(0)
            close = spy_df["Close"]
            spy_entry   = float(close.iloc[-1])
            spy_perf_5d = float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100) if len(close) >= 6 else 0.0
    except Exception:
        pass

    # News
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

- [ ] **Step 3: Ajouter `_call_llm` et `review_pending_trades`**

```python
def _call_llm(trade: dict, enriched: dict, groq_api_key: str) -> TradeReview | None:
    """Appelle Groq pour analyser un trade. Retourne None en cas d'échec."""
    pnl = trade.get("pnl")
    pnl_str = f"+${pnl:.2f}" if (pnl and pnl > 0) else (f"-${abs(pnl):.2f}" if pnl else "inconnu")

    headlines_str = "\n".join(f"- {h}" for h in enriched["headlines"]) or "Aucune news haute impact disponible"

    prompt = REVIEW_PROMPT.format(
        ticker=trade["ticker"],
        direction=trade.get("direction", "LONG"),
        entry=trade.get("entry", 0),
        exit_=trade.get("exit") or 0,
        entry_ts=trade.get("timestamp", "?"),
        exit_ts=trade.get("exit_ts", "?"),
        qty=trade.get("qty", 0),
        pnl_str=pnl_str,
        reasoning=trade.get("reasoning", "Non disponible"),
        spy_perf_5d=enriched["spy_perf_5d"],
        spy_entry=enriched["spy_entry"],
        intraday_prices=enriched["intraday_prices"],
        headlines=headlines_str,
    )

    client = Groq(api_key=groq_api_key)
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            raw  = response.choices[0].message.content.strip()
            data = json.loads(raw)
            return TradeReview(
                ticker=trade["ticker"],
                direction=trade.get("direction", "LONG"),
                entry=trade.get("entry", 0),
                exit_=trade.get("exit") or 0,
                pnl=pnl,
                entry_ts=trade.get("timestamp", ""),
                exit_ts=trade.get("exit_ts", ""),
                signal_score=int(data["signal_score"]),
                timing_score=int(data["timing_score"]),
                sizing_score=int(data["sizing_score"]),
                overall=int(data["overall"]),
                verdict=data["verdict"],
                lesson=data["lesson"],
            )
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 15 * (attempt + 1)
                print(f"[reviewer] 429 rate limit, retry in {wait}s")
                time.sleep(wait)
                continue
            print(f"[reviewer] LLM error for {trade['ticker']}: {e}")
            return None
    return None


def review_pending_trades(
    closed_trades: list[dict],
    existing_reviews: list[dict],
    config: dict,
    max_per_run: int = 5,
) -> list[TradeReview]:
    """Analyse les trades fermés non encore reviewés. Max max_per_run par appel."""
    groq_key = config.get("groq_api_key", "")
    if not groq_key:
        print("[reviewer] No groq_api_key in config, skipping review")
        return []

    reviewed_keys = {
        (r["ticker"], r["entry_ts"])
        for r in existing_reviews
    }

    pending = [
        t for t in closed_trades
        if t.get("pnl") is not None
        and (t["ticker"], t.get("timestamp", "")) not in reviewed_keys
    ][:max_per_run]

    results = []
    for trade in pending:
        print(f"[reviewer] Reviewing {trade['ticker']} ({trade.get('timestamp', '')})...")
        enriched = _fetch_enriched(trade)
        review   = _call_llm(trade, enriched, groq_key)
        if review:
            results.append(review)
            print(f"[reviewer] Done: overall={review.overall}/10")
        else:
            print(f"[reviewer] Skipped (LLM error)")

    return results
```

- [ ] **Step 4: Vérifier que le fichier est syntaxiquement correct**

```bash
python -c "import tools.trade_reviewer; print('OK')"
```

Résultat attendu : `OK`

- [ ] **Step 5: Commit**

```bash
git add tools/trade_reviewer.py
git commit -m "feat: add tools/trade_reviewer — TradeReview dataclass + LLM review logic"
```

---

## Task 2: `bot/persistence.py` — gestion reviews sur Gist

**Files:**
- Modify: `bot/persistence.py`

Les reviews sont stockées dans un fichier `reviews.json` séparé sur le Gist (liste de dicts). La liste `analyses.json` existante n'est pas modifiée.

- [ ] **Step 1: Ajouter `load_reviews_from_gist` à la fin du fichier**

Ouvrir `bot/persistence.py` et ajouter à la fin :

```python
def load_reviews_from_gist(gist_id: str, github_token: str) -> list[dict]:
    resp = requests.get(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {github_token}"},
    )
    if not resp.ok:
        return []
    files = resp.json().get("files", {})
    if "reviews.json" not in files:
        return []
    raw = files["reviews.json"].get("content", "[]")
    return json.loads(raw)
```

- [ ] **Step 2: Modifier `push_to_gist` pour inclure `reviews.json`**

Remplacer la signature et le body de `push_to_gist` :

```python
def push_to_gist(
    html: str,
    analyses: list[dict],
    gist_id: str,
    github_token: str,
    reviews: list[dict] | None = None,
) -> None:
    files: dict = {
        "dashboard.html": {"content": html},
        "analyses.json":  {"content": json.dumps(analyses, indent=2)},
    }
    if reviews is not None:
        files["reviews.json"] = {"content": json.dumps(reviews, indent=2)}

    requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {github_token}"},
        json={"files": files},
    ).raise_for_status()
```

- [ ] **Step 3: Vérifier la syntaxe**

```bash
python -c "from bot.persistence import load_reviews_from_gist, push_to_gist; print('OK')"
```

Résultat attendu : `OK`

- [ ] **Step 4: Commit**

```bash
git add bot/persistence.py
git commit -m "feat: persistence — load_reviews_from_gist, push_to_gist accepts reviews param"
```

---

## Task 3: `bot/dashboard.py` — section Post-Trade Review

**Files:**
- Modify: `bot/dashboard.py`

Ajouter un helper `_render_reviews_section` et l'intégrer dans `render_dashboard`.

- [ ] **Step 1: Ajouter le helper `_render_reviews_section` avant `render_dashboard`**

Ajouter la fonction suivante avant la définition de `render_dashboard` :

```python
def _score_badge(score: int) -> str:
    if score >= 7:
        color = "#3fb950"
        bg    = "#1a3a1a"
    elif score >= 4:
        color = "#d29922"
        bg    = "#2a2a1a"
    else:
        color = "#f85149"
        bg    = "#3a1a1a"
    return f'<span class="badge" style="background:{bg};color:{color}">{score}/10</span>'


def _render_reviews_section(reviews: list[dict]) -> str:
    if not reviews:
        return ""

    recent = sorted(reviews, key=lambda r: r.get("entry_ts", ""), reverse=True)[:30]

    # Indicateurs moyens
    def avg(key):
        vals = [r[key] for r in recent if key in r]
        return sum(vals) / len(vals) if vals else 0.0

    avg_signal = avg("signal_score")
    avg_timing = avg("timing_score")
    avg_sizing = avg("sizing_score")
    avg_overall = avg("overall")

    # KPIs moyens
    kpis = f"""
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
  <div class="kpi"><div class="label">Signal moyen</div><div class="value" style="font-size:1.2em;color:#58a6ff">{avg_signal:.1f}/10</div></div>
  <div class="kpi"><div class="label">Timing moyen</div><div class="value" style="font-size:1.2em;color:#58a6ff">{avg_timing:.1f}/10</div></div>
  <div class="kpi"><div class="label">Sizing moyen</div><div class="value" style="font-size:1.2em;color:#58a6ff">{avg_sizing:.1f}/10</div></div>
  <div class="kpi"><div class="label">Note globale</div><div class="value" style="font-size:1.2em;color:#d29922">{avg_overall:.1f}/10</div></div>
</div>"""

    # Leçons apprises
    lessons = [r["lesson"] for r in recent[:10] if r.get("lesson")]
    lessons_html = "".join(
        f'<li style="padding:6px 0;border-bottom:1px solid #21262d;color:#e6edf3">'
        f'<span style="color:#8b949e;font-size:.8em">{r.get("entry_ts","")[:10]} {r.get("ticker","")}</span> — {r["lesson"]}</li>'
        for r, l in zip(recent[:10], lessons)
    )
    lessons_block = f"""
<div style="background:#161b22;border:1px solid #21262d;border-radius:10px;padding:16px 20px;margin-bottom:20px">
  <div style="font-weight:700;color:#d29922;margin-bottom:10px">Leçons apprises (10 derniers trades)</div>
  <ul style="list-style:none;padding:0;margin:0">{lessons_html}</ul>
</div>"""

    # Tableau des reviews
    rows = ""
    for r in recent:
        direction = r.get("direction", "LONG")
        dir_badge = '<span class="badge short-badge">SHORT</span>' if direction == "SHORT" else '<span class="badge long-badge">LONG</span>'
        pnl = r.get("pnl")
        pnl_color = "#3fb950" if (pnl and pnl > 0) else "#f85149"
        pnl_str   = f'<span style="color:{pnl_color};font-weight:600">{"+" if pnl and pnl > 0 else ""}${pnl:.2f}</span>' if pnl is not None else "—"
        verdict   = r.get("verdict", "")
        short_v   = (verdict[:120] + "…") if len(verdict) > 120 else verdict
        rows += f"""
<tr>
  <td style="white-space:nowrap;color:#8b949e">{r.get("entry_ts","")[:10]}</td>
  <td><strong>{r.get("ticker","")}</strong> {dir_badge}</td>
  <td>{pnl_str}</td>
  <td>{_score_badge(r.get("signal_score", 0))}</td>
  <td>{_score_badge(r.get("timing_score", 0))}</td>
  <td>{_score_badge(r.get("sizing_score", 0))}</td>
  <td>{_score_badge(r.get("overall", 0))}</td>
  <td style="color:#8b949e;font-size:.82em">{short_v}</td>
</tr>"""

    table = f"""
<div class="table-wrap">
<table>
  <thead>
    <tr>
      <th>Date</th><th>Actif</th><th>PnL</th>
      <th>Signal</th><th>Timing</th><th>Sizing</th><th>Global</th><th>Verdict</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
</div>"""

    return kpis + lessons_block + table
```

- [ ] **Step 2: Modifier la signature de `render_dashboard`**

Remplacer :
```python
def render_dashboard(
    positions: list[dict],
    closed_trades: list[dict],
    analyses: list[dict],
    portfolio: dict,
) -> str:
```

Par :
```python
def render_dashboard(
    positions: list[dict],
    closed_trades: list[dict],
    analyses: list[dict],
    portfolio: dict,
    reviews: list[dict] | None = None,
) -> str:
```

- [ ] **Step 3: Injecter la section reviews dans le HTML retourné**

Dans le `return f"""..."""` de `render_dashboard`, ajouter après la section "Trades Clôturés" et avant "Journal des Analyses" :

```python
reviews_section = _render_reviews_section(reviews or [])
```

Ajouter `reviews_section` comme variable locale avant le `return`, puis dans le HTML :

```html
{f'<div class="section-title">Post-Trade Review ({len(reviews or [])} trades analysés)</div>{reviews_section}' if reviews else ''}
```

Concrètement, dans le bloc `return f"""..."""`, repérer la ligne :
```
<div class="section-title">Journal des Analyses ({len(analyses)})</div>
```
et insérer juste avant :
```python
{f'<div class="section-title">Post-Trade Review ({len(reviews or [])} trades analysés)</div>{_render_reviews_section(reviews or [])}' if reviews else ''}
```

- [ ] **Step 4: Vérifier la syntaxe**

```bash
python -c "from bot.dashboard import render_dashboard; print('OK')"
```

Résultat attendu : `OK`

- [ ] **Step 5: Commit**

```bash
git add bot/dashboard.py
git commit -m "feat: dashboard — add post-trade review section with scores and lessons"
```

---

## Task 4: `main.py` — intégration

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Ajouter les imports en tête de `main.py`**

Après les imports existants, ajouter :

```python
from tools.trade_reviewer import review_pending_trades
from bot.persistence import load_reviews_from_gist
```

- [ ] **Step 2: Charger les reviews existantes depuis le Gist**

Dans la fonction `main()`, après la ligne `prior_analyses = load_from_gist(...)`, ajouter :

```python
existing_reviews = load_reviews_from_gist(gist_id, token) if (gist_id and token) else []
```

- [ ] **Step 3: Appeler `review_pending_trades` après la construction de `closed_trades`**

Après la ligne `closed_trades.sort(key=lambda x: x["timestamp"], reverse=True)`, ajouter :

```python
new_reviews = review_pending_trades(
    closed_trades=closed_trades,
    existing_reviews=existing_reviews,
    config=CONFIG,
    max_per_run=5,
)
all_reviews = existing_reviews + [r.to_dict() for r in new_reviews]
```

- [ ] **Step 4: Passer `all_reviews` à `render_dashboard`**

Remplacer l'appel à `render_dashboard` :
```python
html = render_dashboard(
    positions=positions_data,
    closed_trades=closed_trades,
    analyses=analyses_flat[-50:],
    portfolio=portfolio,
)
```
Par :
```python
html = render_dashboard(
    positions=positions_data,
    closed_trades=closed_trades,
    analyses=analyses_flat[-50:],
    portfolio=portfolio,
    reviews=all_reviews[-30:],
)
```

- [ ] **Step 5: Passer `reviews=all_reviews` à `push_to_gist`**

Remplacer :
```python
push_to_gist(html, analyses, gist_id, token)
```
Par :
```python
push_to_gist(html, analyses, gist_id, token, reviews=all_reviews)
```

- [ ] **Step 6: Vérifier la syntaxe globale**

```bash
python -c "import main; print('OK')"
```

Résultat attendu : `OK`

- [ ] **Step 7: Commit**

```bash
git add main.py
git commit -m "feat: main — wire review_pending_trades, load/push reviews on Gist"
```

---

## Validation manuelle

- [ ] Lancer `python main.py` en local avec les variables d'env Alpaca + Groq configurées
- [ ] Vérifier dans les logs la présence de lignes `[reviewer] Reviewing ...`
- [ ] Ouvrir `dashboard.html` généré et vérifier la section "Post-Trade Review"
- [ ] Vérifier que `reviews.json` est bien créé sur le Gist après un run avec trades fermés
