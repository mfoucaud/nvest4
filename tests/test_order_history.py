from tools.order_history import correlate_orders


def _order(side, order_type, filled_price, filled_at, qty=10, symbol="AAPL"):
    return {
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "filled_avg_price": filled_price,
        "filled_at": filled_at,
        "filled_qty": qty,
        "status": "filled",
    }


def test_long_trade_matched():
    orders = [
        _order("buy",  "market",        182.0, "2026-06-10T10:00:00Z"),
        _order("sell", "trailing_stop", 186.0, "2026-06-10T12:00:00Z"),
    ]
    trades = correlate_orders(orders)
    assert len(trades) == 1
    t = trades[0]
    assert t["direction"] == "LONG"
    assert t["entry_price"] == 182.0
    assert t["exit_price"] == 186.0
    assert round(t["pnl"], 2) == 40.0  # (186 - 182) * 10
    assert t["close_type"] == "trailing_stop"
    assert t["win"] is True


def test_short_trade_matched():
    orders = [
        _order("sell", "market",        200.0, "2026-06-10T10:00:00Z"),
        _order("buy",  "trailing_stop", 190.0, "2026-06-10T13:00:00Z"),
    ]
    trades = correlate_orders(orders)
    assert len(trades) == 1
    t = trades[0]
    assert t["direction"] == "SHORT"
    assert t["entry_price"] == 200.0
    assert t["exit_price"] == 190.0
    assert round(t["pnl"], 2) == 100.0  # (200 - 190) * 10
    assert t["close_type"] == "trailing_stop"
    assert t["win"] is True


def test_long_trade_loss():
    orders = [
        _order("buy",  "market",        100.0, "2026-06-10T09:00:00Z"),
        _order("sell", "trailing_stop",  95.0, "2026-06-10T09:30:00Z"),
    ]
    trades = correlate_orders(orders)
    assert trades[0]["pnl"] == -50.0
    assert trades[0]["win"] is False


def test_orphan_entry_no_exit():
    orders = [
        _order("buy", "market", 150.0, "2026-06-10T09:00:00Z"),
    ]
    trades = correlate_orders(orders)
    assert len(trades) == 1
    assert trades[0]["close_type"] == "orphan"
    assert trades[0]["exit_price"] is None
    assert trades[0]["pnl"] is None


def test_multiple_tickers():
    orders = [
        _order("buy",  "market",        100.0, "2026-06-10T09:00:00Z", symbol="AAPL"),
        _order("sell", "trailing_stop", 105.0, "2026-06-10T10:00:00Z", symbol="AAPL"),
        _order("buy",  "market",        200.0, "2026-06-10T09:00:00Z", symbol="TSLA"),
        _order("sell", "trailing_stop", 195.0, "2026-06-10T10:00:00Z", symbol="TSLA"),
    ]
    trades = correlate_orders(orders)
    assert len(trades) == 2
    tickers = {t["ticker"] for t in trades}
    assert tickers == {"AAPL", "TSLA"}


def test_manual_close_detected():
    orders = [
        _order("buy",  "market", 100.0, "2026-06-10T09:00:00Z"),
        _order("sell", "market", 108.0, "2026-06-10T11:00:00Z"),
    ]
    trades = correlate_orders(orders)
    assert trades[0]["close_type"] == "manual"
