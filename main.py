import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus, OrderSide, OrderStatus

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

    # Build stop_id and entry data map from analyses
    stop_id_map: dict[str, str] = {}
    entry_map: dict[str, dict] = {}
    for run in analyses:
        ts = run.get("timestamp", "")
        for trade in run.get("trades", []):
            t = trade["ticker"]
            stop_id_map[t] = trade.get("stop_id", "")
            entry_map[t] = {
                "entry_price": None,  # filled below from position
                "qty":         trade.get("qty", 0),
                "reasoning":   trade.get("reasoning", ""),
                "timestamp":   ts,
            }

    open_tickers = {p.symbol for p in positions}

    positions_data = []
    for p in positions:
        stop_price = None
        sid = stop_id_map.get(p.symbol)
        if sid:
            try:
                stop_order = alpaca.get_order_by_id(sid)
                if stop_order.stop_price:
                    stop_price = float(stop_order.stop_price)
                elif stop_order.trail_price:
                    stop_price = float(stop_order.trail_price)
            except Exception:
                pass
        positions_data.append({
            "ticker":     p.symbol,
            "entry":      float(p.avg_entry_price),
            "current":    float(p.current_price),
            "qty":        int(p.qty),
            "pnl":        float(p.unrealized_pl),
            "pnl_pct":    float(p.unrealized_plpc) * 100,
            "stop_price": stop_price,
            "reasoning":  entry_map.get(p.symbol, {}).get("reasoning", ""),
        })

    # Closed trades: in analyses but no longer in open positions
    seen: set[str] = set()
    closed_trades = []
    for run in reversed(analyses):
        ts = run.get("timestamp", "")
        for trade in run.get("trades", []):
            t = trade["ticker"]
            if t in open_tickers or t in seen:
                continue
            seen.add(t)
            qty = trade.get("qty", 0)
            entry_price = None
            exit_price = None
            # Try to get entry fill price from closed buy order
            bid = trade.get("buy_id")
            if bid:
                try:
                    bo = alpaca.get_order_by_id(bid)
                    if bo.filled_avg_price:
                        entry_price = float(bo.filled_avg_price)
                except Exception:
                    pass
            # Try to get exit price from most recent filled sell order for this ticker
            try:
                sell_orders = alpaca.get_orders(filter=GetOrdersRequest(
                    status=QueryOrderStatus.CLOSED,
                    symbols=[t],
                    side=OrderSide.SELL,
                ))
                filled_sells = [o for o in sell_orders if o.status == OrderStatus.FILLED and o.filled_avg_price]
                if filled_sells:
                    exit_price = float(filled_sells[0].filled_avg_price)
            except Exception:
                pass
            realized_pnl = None
            if entry_price and exit_price and qty:
                realized_pnl = (exit_price - entry_price) * qty
            closed_trades.append({
                "ticker":       t,
                "entry":        entry_price,
                "exit":         exit_price,
                "qty":          qty,
                "pnl":          realized_pnl,
                "reasoning":    trade.get("reasoning", ""),
                "timestamp":    ts,
            })

    won  = sum(1 for c in closed_trades if c["pnl"] is not None and c["pnl"] > 0)
    lost = sum(1 for c in closed_trades if c["pnl"] is not None and c["pnl"] <= 0)
    total_closed = len([c for c in closed_trades if c["pnl"] is not None])

    portfolio = {
        "capital":      float(account.portfolio_value),
        "pnl":          float(account.equity) - float(account.last_equity),
        "trades":       sum(len(a.get("trades", [])) for a in analyses),
        "win_rate":     (won / total_closed * 100) if total_closed else 0.0,
        "wins":         won,
        "losses":       lost,
    }

    html = render_dashboard(
        positions=positions_data,
        closed_trades=closed_trades,
        analyses=analyses_flat[-50:],
        portfolio=portfolio,
    )

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
