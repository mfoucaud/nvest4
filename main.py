import os
from collections import defaultdict
from datetime import datetime, timezone
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus, OrderSide, OrderStatus

from bot.runner import run_cycle
from bot.dashboard import render_dashboard
from bot.persistence import append_run, load_from_gist, push_to_gist, load_reviews_from_gist
from tools.trade_reviewer import review_pending_trades

load_dotenv()

WATCHLIST = [
    # Momentum high-beta
    "NVDA", "AMD", "SMCI", "PLTR", "COIN", "MSTR", "RDDT", "CRWD", "ANET", "UBER",
    # Mega-caps momentum (conservés)
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "ADBE",
    # Energie (geopolitique Iran/pétrole)
    "XOM", "CVX", "OXY", "SCO", "DRIP",
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
    existing_reviews = load_reviews_from_gist(gist_id, token) if (gist_id and token) else []

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

    # Reasoning map from analyses (best-effort enrichment)
    reasoning_map: dict[str, str] = {}
    for run in analyses:
        for trade in run.get("trades", []):
            reasoning_map[trade["ticker"]] = trade.get("reasoning", "")

    open_tickers = {p.symbol for p in positions}

    # Fetch all orders from Alpaca (source of truth)
    all_buy_orders = alpaca.get_orders(filter=GetOrdersRequest(
        status=QueryOrderStatus.CLOSED,
        side=OrderSide.BUY,
        limit=200,
    ))
    all_sell_orders = alpaca.get_orders(filter=GetOrdersRequest(
        status=QueryOrderStatus.CLOSED,
        side=OrderSide.SELL,
        limit=200,
    ))

    def _is_trailing_stop(order) -> bool:
        return bool(order.trail_percent or order.trail_price)

    filled_closed = [
        o for o in all_buy_orders + all_sell_orders
        if o.status == OrderStatus.FILLED and o.filled_avg_price
    ]

    # Long entries: market BUY filled
    long_entries  = sorted(
        [o for o in filled_closed if o.side == OrderSide.BUY  and not _is_trailing_stop(o)],
        key=lambda x: x.filled_at,
    )
    # Long exits: trailing stop SELL filled
    long_exits_by_ticker: dict[str, list] = defaultdict(list)
    for o in sorted(
        [o for o in filled_closed if o.side == OrderSide.SELL and _is_trailing_stop(o)],
        key=lambda x: x.filled_at,
    ):
        long_exits_by_ticker[o.symbol].append(o)

    # Short entries: market SELL filled
    short_entries = sorted(
        [o for o in filled_closed if o.side == OrderSide.SELL and not _is_trailing_stop(o)],
        key=lambda x: x.filled_at,
    )
    # Short exits: trailing stop BUY filled
    short_exits_by_ticker: dict[str, list] = defaultdict(list)
    for o in sorted(
        [o for o in filled_closed if o.side == OrderSide.BUY  and _is_trailing_stop(o)],
        key=lambda x: x.filled_at,
    ):
        short_exits_by_ticker[o.symbol].append(o)

    # Open stop orders — stop price for open positions
    open_stops_long  = alpaca.get_orders(filter=GetOrdersRequest(
        status=QueryOrderStatus.OPEN, side=OrderSide.SELL,
    ))
    open_stops_short = alpaca.get_orders(filter=GetOrdersRequest(
        status=QueryOrderStatus.OPEN, side=OrderSide.BUY,
    ))
    stop_price_map: dict[str, float] = {}
    for o in list(open_stops_long) + list(open_stops_short):
        if not _is_trailing_stop(o):
            continue
        price = float(o.stop_price) if o.stop_price else (float(o.trail_price) if o.trail_price else None)
        if price:
            stop_price_map[o.symbol] = price

    positions_data = []
    for p in positions:
        is_short = hasattr(p, "side") and str(p.side).lower() == "short"
        positions_data.append({
            "ticker":     p.symbol,
            "direction":  "SHORT" if is_short else "LONG",
            "entry":      float(p.avg_entry_price),
            "current":    float(p.current_price),
            "qty":        abs(int(float(p.qty))),
            "pnl":        float(p.unrealized_pl),
            "pnl_pct":    float(p.unrealized_plpc) * 100,
            "stop_price": stop_price_map.get(p.symbol),
            "reasoning":  reasoning_map.get(p.symbol, ""),
        })

    def _pair_trades(entries, exits_by_ticker, direction: str) -> list[dict]:
        cursor: dict[str, int] = defaultdict(int)
        result = []
        for entry in entries:
            ticker = entry.symbol
            if ticker in open_tickers:
                continue
            exit_list = exits_by_ticker.get(ticker, [])
            idx = cursor[ticker]
            paired = None
            for i in range(idx, len(exit_list)):
                if exit_list[i].filled_at >= entry.filled_at:
                    paired = exit_list[i]
                    cursor[ticker] = i + 1
                    break
            entry_price  = float(entry.filled_avg_price)
            exit_price   = float(paired.filled_avg_price) if paired else None
            qty          = int(float(entry.filled_qty))
            if direction == "LONG":
                realized_pnl = (exit_price - entry_price) * qty if exit_price else None
            else:
                realized_pnl = (entry_price - exit_price) * qty if exit_price else None
            ts = entry.filled_at.strftime("%Y-%m-%d %H:%M") if entry.filled_at else ""
            result.append({
                "ticker":    ticker,
                "direction": direction,
                "entry":     entry_price,
                "exit":      exit_price,
                "qty":       qty,
                "pnl":       realized_pnl,
                "reasoning": reasoning_map.get(ticker, ""),
                "timestamp": ts,
            })
        return result

    closed_trades = (
        _pair_trades(long_entries,  long_exits_by_ticker,  "LONG") +
        _pair_trades(short_entries, short_exits_by_ticker, "SHORT")
    )
    closed_trades.sort(key=lambda x: x["timestamp"], reverse=True)

    new_reviews = review_pending_trades(
        closed_trades=closed_trades,
        existing_reviews=existing_reviews,
        config=CONFIG,
        max_per_run=5,
    )
    all_reviews = existing_reviews + [r.to_dict() for r in new_reviews]

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
        reviews=all_reviews[-30:],
    )

    if gist_id and token:
        push_to_gist(html, analyses, gist_id, token, reviews=all_reviews)
        print("Dashboard pushed to Gist.")
    else:
        with open("dashboard.html", "w") as f:
            f.write(html)
        print("Dashboard saved locally (GIST_ID ou GITHUB_TOKEN manquant).")

    print("=== !nvest4 run complete ===")


if __name__ == "__main__":
    main()
