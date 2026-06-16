from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os

from colorama import Fore


# ── Corrélation ──────────────────────────────────────────────────────────────

def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _make_orphan(ticker: str, pending: dict) -> dict:
    entry_o = pending["order"]
    return {
        "ticker":       ticker,
        "direction":    pending["direction"],
        "entry_price":  float(entry_o["filled_avg_price"]),
        "exit_price":   None,
        "qty":          float(entry_o["filled_qty"]),
        "pnl":          None,
        "duration_min": None,
        "win":          None,
        "close_type":   "orphan",
        "entry_time":   entry_o["filled_at"],
        "exit_time":    None,
        "reasoning":    "",
    }


def correlate_orders(orders: list[dict]) -> list[dict]:
    """
    Corrèle les ordres d'entrée avec leurs ordres de sortie par ticker.

    LONG  : entrée = BUY market,  sortie = SELL (trailing_stop ou market)
    SHORT : entrée = SELL market, sortie = BUY  (trailing_stop ou market)

    Retourne une liste de trades avec les champs :
    ticker, direction, entry_price, exit_price, qty, pnl, duration_min,
    win, close_type, entry_time, exit_time

    Note : les fills partiels ne sont pas supportés (qty entry == qty exit supposé).
    """
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for o in orders:
        if o.get("status") == "filled":
            by_ticker[o["symbol"]].append(o)

    trades = []
    for ticker, ticker_orders in by_ticker.items():
        ticker_orders.sort(key=lambda o: o["filled_at"])
        pending_entry = None

        for o in ticker_orders:
            side = o["side"]
            order_type = o.get("order_type", "market")
            price = float(o["filled_avg_price"])
            qty = float(o["filled_qty"])
            filled_at = o["filled_at"]

            if pending_entry is None:
                # Nouvel ordre d'entrée
                if side == "buy" and order_type == "market":
                    pending_entry = {"direction": "LONG", "order": o}
                elif side == "sell" and order_type == "market":
                    pending_entry = {"direction": "SHORT", "order": o}
                elif side == "sell" and order_type == "trailing_stop":
                    print(f"[warn] {ticker}: SELL trailing_stop sans entrée ouverte — ignoré (résidu ou position externe)")
                elif side == "buy" and order_type == "trailing_stop":
                    print(f"[warn] {ticker}: BUY trailing_stop sans entrée SHORT ouverte — ignoré (résidu ou position externe)")
            else:
                direction = pending_entry["direction"]
                entry_o = pending_entry["order"]
                entry_price = float(entry_o["filled_avg_price"])
                entry_qty = float(entry_o["filled_qty"])
                entry_time = entry_o["filled_at"]

                is_exit = (
                    (direction == "LONG"  and side == "sell") or
                    (direction == "SHORT" and side == "buy")
                )

                if is_exit:
                    pnl = (
                        (price - entry_price) * entry_qty
                        if direction == "LONG"
                        else (entry_price - price) * entry_qty
                    )
                    duration_min = (
                        (_parse_dt(filled_at) - _parse_dt(entry_time)).total_seconds() / 60
                    )
                    close_type = "trailing_stop" if order_type == "trailing_stop" else "manual"
                    trades.append({
                        "ticker":       ticker,
                        "direction":    direction,
                        "entry_price":  entry_price,
                        "exit_price":   price,
                        "qty":          entry_qty,
                        "pnl":          round(pnl, 2),
                        "duration_min": round(duration_min, 1),
                        "win":          pnl > 0,
                        "close_type":   close_type,
                        "entry_time":   entry_time,
                        "exit_time":    filled_at,
                        "reasoning":    "",
                    })
                    pending_entry = None
                else:
                    # Nouvel ordre d'entrée dans le même sens → on clôt l'ancien comme orphelin
                    trades.append(_make_orphan(ticker, pending_entry))
                    # Nouveau pending
                    if side == "buy" and order_type == "market":
                        pending_entry = {"direction": "LONG", "order": o}
                    elif side == "sell" and order_type == "market":
                        pending_entry = {"direction": "SHORT", "order": o}
                    else:
                        pending_entry = None

        # Entrée sans sortie en fin de liste
        if pending_entry:
            trades.append(_make_orphan(ticker, pending_entry))

    trades.sort(key=lambda t: t["entry_time"])
    return trades


def fetch_orders(api_key: str, api_secret: str, days: int) -> list[dict]:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    client = TradingClient(api_key, api_secret, paper=True)
    after = datetime.now(timezone.utc) - timedelta(days=days)

    req = GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        after=after,
        limit=500,
    )
    raw_orders = client.get_orders(req)

    return [
        {
            "symbol":           o.symbol,
            "side":             o.side.value,
            "order_type":       o.type.value,
            "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
            "filled_at":        o.filled_at.isoformat() if o.filled_at else None,
            "filled_qty":       str(o.filled_qty) if o.filled_qty else None,
            "status":           o.status.value,
            "id":               str(o.id),
        }
        for o in raw_orders
        if o.status.value == "filled"
        and o.filled_avg_price is not None
        and o.filled_qty is not None
        and o.filled_at is not None
    ]


def enrich_with_analyses(trades: list[dict], analyses_path: str) -> list[dict]:
    if not os.path.exists(analyses_path):
        print(f"{Fore.YELLOW}[warn] {analyses_path} introuvable, enrichissement ignoré.")
        return trades

    with open(analyses_path) as f:
        analyses = json.load(f)

    # Enrichissement par ticker (fallback sans buy_id dans les trades corrélés)
    for trade in trades:
        for run in analyses:
            found = False
            for at in run.get("trades", []):
                if at.get("ticker") != trade["ticker"]:
                    continue
                reasoning = at.get("reasoning", "")
                if reasoning:
                    trade["reasoning"] = reasoning
                    found = True
                    break
            if found:
                break

    return trades
