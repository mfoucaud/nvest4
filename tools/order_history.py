from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import argparse
import csv
import json
import os

from colorama import Fore, Style
from tabulate import tabulate


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


def _fmt_pnl(pnl) -> str:
    if pnl is None:
        return "—"
    sign = "+" if pnl >= 0 else ""
    color = Fore.GREEN if pnl >= 0 else Fore.RED
    return f"{color}{sign}${pnl:.2f}{Style.RESET_ALL}"


def _fmt_duration(minutes) -> str:
    if minutes is None:
        return "—"
    if minutes < 60:
        return f"{int(minutes)}m"
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h}h{m:02d}m"


def print_report(trades: list[dict]) -> None:
    completed = [t for t in trades if t["close_type"] != "orphan"]
    orphans   = [t for t in trades if t["close_type"] == "orphan"]

    # ── KPIs globaux ──
    total = len(completed)
    wins  = sum(1 for t in completed if t.get("win"))
    pnl_total = sum(t["pnl"] for t in completed if t["pnl"] is not None)
    win_rate = (wins / total * 100) if total else 0

    pnl_color = Fore.GREEN if pnl_total >= 0 else Fore.RED
    print()
    print("═" * 60)
    print(f"  {Style.BRIGHT}KPIs GLOBAUX{Style.RESET_ALL}")
    print(f"  Trades : {total}  |  Win Rate : {Fore.YELLOW}{win_rate:.0f}%{Style.RESET_ALL}  |  PnL Total : {pnl_color}{'+'if pnl_total>=0 else ''}${pnl_total:.2f}{Style.RESET_ALL}")
    print("═" * 60)
    print()

    # ── Tableau trades ──
    rows = []
    for t in completed:
        dir_color = Fore.CYAN if t["direction"] == "LONG" else Fore.MAGENTA
        rows.append([
            t["ticker"],
            f"{dir_color}{t['direction']}{Style.RESET_ALL}",
            f"${t['entry_price']:.2f}",
            f"${t['exit_price']:.2f}" if t["exit_price"] else "—",
            int(t["qty"]) if t.get("qty") is not None else "—",
            _fmt_pnl(t["pnl"]),
            _fmt_duration(t["duration_min"]),
            f"{Fore.GREEN}WIN{Style.RESET_ALL}" if t.get("win") else f"{Fore.RED}LOSS{Style.RESET_ALL}",
            t["close_type"],
        ])
    headers = ["Ticker", "Dir", "Entrée", "Sortie", "Qté", "PnL", "Durée", "Résultat", "Clôture"]
    print(f"{Style.BRIGHT}TRADES ({len(completed)}){Style.RESET_ALL}")
    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print()

    # ── Stats par ticker ──
    by_ticker: dict[str, list] = defaultdict(list)
    for t in completed:
        by_ticker[t["ticker"]].append(t)

    stat_rows = []
    for ticker, ticker_trades in sorted(by_ticker.items()):
        tw = [t for t in ticker_trades if t.get("win")]
        pnls = [t["pnl"] for t in ticker_trades if t["pnl"] is not None]
        durs = [t["duration_min"] for t in ticker_trades if t["duration_min"] is not None]
        stat_rows.append([
            ticker,
            len(ticker_trades),
            f"{Fore.YELLOW}{len(tw)/len(ticker_trades)*100:.0f}%{Style.RESET_ALL}",
            _fmt_pnl(sum(pnls)/len(pnls) if pnls else None),
            _fmt_duration(sum(durs)/len(durs) if durs else None),
        ])
    print(f"{Style.BRIGHT}STATS PAR TICKER{Style.RESET_ALL}")
    print(tabulate(stat_rows, headers=["Ticker", "Trades", "Win Rate", "PnL Moyen", "Durée Moy"], tablefmt="simple"))

    if orphans:
        print()
        print(f"{Fore.YELLOW}Positions orphelines (entrée sans sortie) : {', '.join(t['ticker'] for t in orphans)}{Style.RESET_ALL}")
    print()


def export_csv(trades: list[dict], path: str) -> None:
    fields = [
        "ticker", "direction", "entry_price", "exit_price", "qty",
        "pnl", "duration_min", "win", "close_type",
        "entry_time", "exit_time", "reasoning",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    print(f"{Fore.GREEN}Export CSV : {path}{Style.RESET_ALL}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Historique des ordres Alpaca avec corrélation PnL")
    parser.add_argument("--days",     type=int,  default=30,  help="Nombre de jours d'historique (défaut: 30)")
    parser.add_argument("--output",   type=str,  default=None, help="Chemin export CSV optionnel")
    parser.add_argument("--analyses", type=str,  default=None, help="Chemin vers analyses.json pour enrichissement")
    args = parser.parse_args()

    api_key    = os.getenv("ALPACA_KEY")
    api_secret = os.getenv("ALPACA_SECRET")
    if not api_key or not api_secret:
        print(f"{Fore.RED}[erreur] Variables ALPACA_KEY et ALPACA_SECRET requises.{Style.RESET_ALL}")
        raise SystemExit(1)

    try:
        print(f"Récupération des ordres des {args.days} derniers jours...")
        orders = fetch_orders(api_key, api_secret, args.days)
        print(f"{len(orders)} ordres filled récupérés.")
    except Exception as e:
        print(f"{Fore.RED}[erreur] Impossible de récupérer les ordres Alpaca : {e}{Style.RESET_ALL}")
        raise SystemExit(1)

    trades = correlate_orders(orders)

    if args.analyses:
        try:
            trades = enrich_with_analyses(trades, args.analyses)
        except Exception as e:
            print(f"{Fore.YELLOW}[warn] Enrichissement échoué : {e}{Style.RESET_ALL}")

    print_report(trades)

    if args.output:
        export_csv(trades, args.output)


if __name__ == "__main__":
    main()
