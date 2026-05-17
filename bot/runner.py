from dataclasses import dataclass, field

from alpaca.trading.client import TradingClient

from bot.scanner import scan_watchlist
from bot.news import classify_news
from bot.llm import get_decision, Action
from bot.risk import validate_order
from bot.trader import execute_order


def get_account(client):
    return client.get_account()


def get_positions(client):
    return client.get_all_positions()


@dataclass
class RunSummary:
    analysed: list[str]             = field(default_factory=list)
    trades:   list[dict]            = field(default_factory=list)
    skipped:  list[dict]            = field(default_factory=list)


def run_cycle(watchlist: list[str], config: dict) -> RunSummary:
    alpaca = TradingClient(config["alpaca_key"], config["alpaca_secret"], paper=True)
    account   = get_account(alpaca)
    positions = get_positions(alpaca)
    open_tickers = [p.symbol for p in positions]
    capital      = float(account.cash)

    signals  = scan_watchlist(watchlist)
    summary  = RunSummary()

    for signal in signals:
        ticker   = signal.ticker
        print(f"[runner] analysing {ticker}...")
        summary.analysed.append(ticker)

        news_items = classify_news(ticker)
        headlines  = [n.headline for n in news_items]

        decision = get_decision(
            ticker=ticker,
            signals=signal.signals,
            headlines=headlines,
            open_positions=open_tickers,
            capital=capital,
            api_key=config["api_key"],
        )

        if decision.action != Action.BUY:
            summary.skipped.append({"ticker": ticker, "reason": decision.action.value, "reasoning": decision.reasoning})
            continue

        order = validate_order(
            ticker=ticker,
            price=signal.close,
            capital=capital,
            open_positions=open_tickers,
        )

        if not order.approved:
            summary.skipped.append({"ticker": ticker, "reason": order.rejection.value})
            continue

        result = execute_order(alpaca, ticker=ticker, qty=order.qty, trail_percent=5.0)
        summary.trades.append({
            "ticker":    ticker,
            "qty":       order.qty,
            "buy_id":    result.buy_id,
            "stop_id":   result.stop_id,
            "reasoning": decision.reasoning,
        })
        open_tickers.append(ticker)

    return summary
