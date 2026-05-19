from dataclasses import dataclass
from enum import Enum

MAX_POSITIONS       = 10
POSITION_PCT        = 0.10   # 10% du capital par position
STOP_LOSS_PCT       = 0.05   # stop loss à -5%


class RejectionReason(Enum):
    MAX_POSITIONS_REACHED = "max_positions_reached"
    ALREADY_OPEN          = "already_open"
    INSUFFICIENT_BUDGET   = "insufficient_budget"


@dataclass
class OrderRequest:
    ticker:     str
    approved:   bool
    qty:        int                    = 0
    stop_price: float                  = 0.0
    rejection:  RejectionReason | None = None


def validate_order(
    ticker:         str,
    price:          float,
    capital:        float,
    open_positions: list[str],
) -> OrderRequest:
    if ticker in open_positions:
        return OrderRequest(ticker=ticker, approved=False, rejection=RejectionReason.ALREADY_OPEN)

    if len(open_positions) >= MAX_POSITIONS:
        return OrderRequest(ticker=ticker, approved=False, rejection=RejectionReason.MAX_POSITIONS_REACHED)

    budget = capital * POSITION_PCT
    qty    = int(budget // price)

    if qty == 0:
        return OrderRequest(ticker=ticker, approved=False, rejection=RejectionReason.INSUFFICIENT_BUDGET)

    return OrderRequest(
        ticker=ticker,
        approved=True,
        qty=qty,
        stop_price=round(price * (1 - STOP_LOSS_PCT), 4),
    )
