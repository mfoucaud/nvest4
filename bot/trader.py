import time
from dataclasses import dataclass

from alpaca.trading.requests import MarketOrderRequest, TrailingStopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus

POLL_INTERVAL = 1  # seconde


@dataclass
class TradeResult:
    ticker:  str
    success: bool
    buy_id:  str = ""
    stop_id: str = ""


def execute_order(
    client,
    ticker:       str,
    qty:          int,
    trail_percent: float,
    poll_timeout: int = 60,
) -> TradeResult:
    buy_order = client.submit_order(MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    ))

    for _ in range(poll_timeout):
        if client.get_order_by_id(buy_order.id).status == OrderStatus.FILLED:
            break
        time.sleep(POLL_INTERVAL)
    else:
        client.cancel_order_by_id(buy_order.id)
        raise TimeoutError(
            f"{ticker}: BUY non filled après {poll_timeout}s — ordre annulé"
        )

    stop_order = client.submit_order(TrailingStopOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.GTC,
        trail_percent=trail_percent,
    ))

    return TradeResult(
        ticker=ticker,
        success=True,
        buy_id=buy_order.id,
        stop_id=stop_order.id,
    )
