# bot/runner.py
from dataclasses import dataclass, field

from alpaca.trading.client import TradingClient

from bot.scanner import scan_watchlist
from bot.news import classify_news
from bot.llm import get_llm_provider, Action
from bot.risk import validate_order
from bot.trader import execute_order, execute_short_order
from bot.market_regime import get_market_regime

CONFIDENCE_MIN         = 0.65
CONFIDENCE_MIN_NEUTRAL = 0.75


def compute_trail_pct(atr: float, close: float) -> float:
    """Trailing stop adaptatif : 2×ATR/prix, borné entre 3% et 10%."""
    if close <= 0 or atr <= 0:
        return 5.0
    pct = round(2 * atr / close * 100, 1)
    return max(3.0, min(10.0, pct))


def get_account(client):
    return client.get_account()


def get_positions(client):
    return client.get_all_positions()


@dataclass
class RunSummary:
    analysed: list[str]  = field(default_factory=list)
    trades:   list[dict] = field(default_factory=list)
    skipped:  list[dict] = field(default_factory=list)


def run_cycle(watchlist: list[str], config: dict) -> RunSummary:
    alpaca       = TradingClient(config["alpaca_key"], config["alpaca_secret"], paper=True)
    account      = get_account(alpaca)
    positions    = get_positions(alpaca)
    open_tickers = [p.symbol for p in positions]
    capital      = float(account.cash)

    regime = get_market_regime()
    print(f"[runner] Market regime: {regime.regime} | SPY 5j: {regime.spy_perf_5d:+.1f}%")

    llm     = get_llm_provider(config)
    signals = scan_watchlist(watchlist)
    summary = RunSummary()

    for signal in signals:
        ticker = signal.ticker
        print(f"[runner] analysing {ticker}...")
        summary.analysed.append(ticker)

        news_items    = classify_news(ticker)
        headlines     = [n.headline for n in news_items if n.high_impact]
        trail_pct     = compute_trail_pct(signal.atr, signal.close)

        # Intentional stub: scanner only exposes the latest close.
        # The LLM prompt benefits from the market regime and ATR context
        # already provided; multi-point price history is a future improvement.
        recent_prices: list[float] = [signal.close]

        decision = llm.get_decision(
            ticker=ticker,
            signals=signal.signals,
            headlines=headlines,
            open_positions=open_tickers,
            capital=capital,
            market_regime=regime.regime,
            spy_perf_5d=regime.spy_perf_5d,
            recent_prices=recent_prices,
            atr=signal.atr,
            trail_pct=trail_pct,
        )

        if decision.action == Action.HOLD:
            summary.skipped.append({"ticker": ticker, "reason": "HOLD",
                                     "reasoning": decision.reasoning})
            continue

        # Filtre confiance minimum
        min_conf = CONFIDENCE_MIN_NEUTRAL if regime.regime == "NEUTRAL" else CONFIDENCE_MIN
        if decision.confidence < min_conf:
            summary.skipped.append({
                "ticker": ticker,
                "reason": f"LOW_CONFIDENCE({decision.confidence:.2f}<{min_conf})",
                "reasoning": decision.reasoning,
            })
            continue

        # Blocage des décisions contradictoires avec le régime
        if regime.regime == "BULL" and decision.action == Action.SELL:
            summary.skipped.append({"ticker": ticker, "reason": "REGIME_CONFLICT(BULL+SELL)",
                                     "reasoning": decision.reasoning})
            continue
        if regime.regime == "BEAR" and decision.action == Action.BUY:
            summary.skipped.append({"ticker": ticker, "reason": "REGIME_CONFLICT(BEAR+BUY)",
                                     "reasoning": decision.reasoning})
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

        direction = decision.action.value
        try:
            if decision.action == Action.BUY:
                result = execute_order(alpaca, ticker=ticker, qty=order.qty,
                                       trail_percent=trail_pct)
            else:
                result = execute_short_order(alpaca, ticker=ticker, qty=order.qty,
                                             trail_percent=trail_pct)
        except (TimeoutError, RuntimeError) as e:
            print(f"[runner] {e}")
            summary.skipped.append({"ticker": ticker, "reason": "TIMEOUT", "reasoning": str(e)})
            continue

        summary.trades.append({
            "ticker":    ticker,
            "qty":       order.qty,
            "direction": direction,
            "buy_id":    result.buy_id,
            "stop_id":   result.stop_id,
            "reasoning": decision.reasoning,
        })
        open_tickers.append(ticker)

    return summary
