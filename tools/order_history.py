from __future__ import annotations
from collections import defaultdict
from datetime import datetime


# ── Corrélation ──────────────────────────────────────────────────────────────

def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def correlate_orders(orders: list[dict]) -> list[dict]:
    """
    Corrèle les ordres d'entrée avec leurs ordres de sortie par ticker.

    LONG  : entrée = BUY market,  sortie = SELL (trailing_stop ou market)
    SHORT : entrée = SELL market, sortie = BUY  (trailing_stop ou market)

    Retourne une liste de trades avec les champs :
    ticker, direction, entry_price, exit_price, qty, pnl, duration_min,
    win, close_type, entry_time, exit_time
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
                # SELL trailing_stop sans entrée ouverte → ignorer (résidu)
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
                    entry_o2 = pending_entry["order"]
                    trades.append({
                        "ticker":       ticker,
                        "direction":    pending_entry["direction"],
                        "entry_price":  float(entry_o2["filled_avg_price"]),
                        "exit_price":   None,
                        "qty":          float(entry_o2["filled_qty"]),
                        "pnl":          None,
                        "duration_min": None,
                        "win":          None,
                        "close_type":   "orphan",
                        "entry_time":   entry_o2["filled_at"],
                        "exit_time":    None,
                        "reasoning":    "",
                    })
                    # Nouveau pending
                    if side == "buy" and order_type == "market":
                        pending_entry = {"direction": "LONG", "order": o}
                    elif side == "sell" and order_type == "market":
                        pending_entry = {"direction": "SHORT", "order": o}
                    else:
                        pending_entry = None

        # Entrée sans sortie en fin de liste
        if pending_entry:
            entry_o = pending_entry["order"]
            trades.append({
                "ticker":       ticker,
                "direction":    pending_entry["direction"],
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
            })

    trades.sort(key=lambda t: t["entry_time"])
    return trades
