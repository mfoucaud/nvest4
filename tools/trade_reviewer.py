# tools/trade_reviewer.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
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
    stored_regime   = trade.get("market_regime")
    stored_spy_perf = trade.get("spy_perf_5d")
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


def _safe_score(value, default: int = 0) -> int:
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return default


def _call_llm(trade: dict, enriched: dict, client: Groq) -> TradeReview | None:
    """Appelle Groq pour analyser un trade. Retourne None en cas d'échec."""
    pnl = trade.get("pnl")
    if pnl is None:
        pnl_str = "inconnu"
    elif pnl > 0:
        pnl_str = f"+${pnl:.2f}"
    elif pnl < 0:
        pnl_str = f"-${abs(pnl):.2f}"
    else:
        pnl_str = "$0.00 (breakeven)"

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
                signal_score=_safe_score(data.get("signal_score")),
                timing_score=_safe_score(data.get("timing_score")),
                sizing_score=_safe_score(data.get("sizing_score")),
                overall=_safe_score(data.get("overall")),
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
    client = Groq(api_key=groq_key)

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
        review   = _call_llm(trade, enriched, client)
        if review:
            results.append(review)
            print(f"[reviewer] Done: overall={review.overall}/10")
        else:
            print(f"[reviewer] Skipped (LLM error)")

    return results
