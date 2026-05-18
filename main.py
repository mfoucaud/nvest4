import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

from bot.runner import run_cycle
from bot.dashboard import render_dashboard
from bot.persistence import append_run, load_from_gist, push_to_gist

load_dotenv()

WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    "JPM", "BAC", "WMT", "JNJ", "PG", "XOM", "CVX", "KO",
    "PEP", "DIS", "NFLX", "ADBE", "CRM",
]

CONFIG = {
    "llm_provider":  os.environ.get("LLM_PROVIDER", "groq"),
    "groq_api_key":  os.environ.get("GROQ_API_KEY", ""),
    "gemini_api_key": os.environ.get("GOOGLEAI_STUDIO_API_KEY", ""),
    "alpaca_key":    os.environ["ALPACA_API_KEY"],
    "alpaca_secret": os.environ["ALPACA_API_SECRET"],
}


def main():
    print("=== !nvest4 run start ===")

    summary = run_cycle(watchlist=WATCHLIST, config=CONFIG)
    print(f"Analysed: {summary.analysed}")
    print(f"Trades:   {len(summary.trades)}")
    print(f"Skipped:  {len(summary.skipped)}")

    gist_id = os.environ.get("GIST_ID")
    token   = os.environ.get("GITHUB_TOKEN")

    prior_analyses = load_from_gist(gist_id, token) if (gist_id and token) else None

    run_dict = {
        "analysed": summary.analysed,
        "trades":   summary.trades,
        "skipped":  summary.skipped,
    }
    analyses = append_run(run_dict, analyses=prior_analyses)

    analyses_flat = []
    for run in analyses:
        ts = run.get("timestamp", "")
        for t in run.get("trades", []):
            analyses_flat.append({"timestamp": ts, "ticker": t["ticker"],
                                   "action": "BUY", "traded": True, "reasoning": t.get("reasoning", "")})
        for s in run.get("skipped", []):
            analyses_flat.append({"timestamp": ts, "ticker": s["ticker"],
                                   "action": s.get("reason", "SKIP"), "traded": False, "reasoning": s.get("reasoning", "")})

    alpaca   = TradingClient(CONFIG["alpaca_key"], CONFIG["alpaca_secret"], paper=True)
    account  = alpaca.get_account()
    positions = alpaca.get_all_positions()

    positions_data = [
        {
            "ticker":    p.symbol,
            "entry":     float(p.avg_entry_price),
            "current":   float(p.current_price),
            "qty":       int(p.qty),
            "pnl":       float(p.unrealized_pl),
            "reasoning": next(
                (t["reasoning"] for t in reversed(analyses)
                 for trade in [t] if any(tr["ticker"] == p.symbol for tr in t.get("trades", []))),
                "",
            ),
        }
        for p in positions
    ]

    portfolio = {
        "capital":  float(account.portfolio_value),
        "pnl":      float(account.equity) - float(account.last_equity),
        "trades":   sum(len(a.get("trades", [])) for a in analyses),
        "win_rate": 0.0,  # calculé par l'outil de supervision (phase 2)
    }

    html = render_dashboard(positions=positions_data, analyses=analyses_flat[-50:], portfolio=portfolio)

    if gist_id and token:
        push_to_gist(html, analyses, gist_id, token)
        print("Dashboard pushed to Gist.")
    else:
        with open("dashboard.html", "w") as f:
            f.write(html)
        print("Dashboard saved locally (GIST_ID ou GITHUB_TOKEN manquant).")

    print("=== !nvest4 run complete ===")


if __name__ == "__main__":
    main()
