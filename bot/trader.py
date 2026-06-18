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

    try:
        stop_order = client.submit_order(TrailingStopOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            trail_percent=trail_percent,
        ))
    except Exception as e:
        client.close_position(ticker)
        raise RuntimeError(
            f"{ticker}: trailing stop refusé ({e}) — position liquidée"
        ) from e

    return TradeResult(
        ticker=ticker,
        success=True,
        buy_id=str(buy_order.id),
        stop_id=str(stop_order.id),
    )


def execute_short_order(
    client,
    ticker:        str,
    qty:           int,
    trail_percent: float,
    poll_timeout:  int = 60,
) -> TradeResult:
    short_order = client.submit_order(MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    ))

    for _ in range(poll_timeout):
        if client.get_order_by_id(short_order.id).status == OrderStatus.FILLED:
            break
        time.sleep(POLL_INTERVAL)
    else:
        client.cancel_order_by_id(short_order.id)
        raise TimeoutError(
            f"{ticker}: SHORT non filled après {poll_timeout}s — ordre annulé"
        )

    try:
        cover_order = client.submit_order(TrailingStopOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            trail_percent=trail_percent,
        ))
    except Exception as e:
        client.close_position(ticker)
        raise RuntimeError(
            f"{ticker}: trailing stop BUY refusé ({e}) — position couverte"
        ) from e

    return TradeResult(
        ticker=ticker,
        success=True,
        buy_id=str(short_order.id),
        stop_id=str(cover_order.id),
    )
