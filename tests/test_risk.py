import pytest
from bot.risk import validate_order, OrderRequest, RejectionReason


class TestPositionSizing:
    def test_qty_is_10_percent_of_capital(self):
        order = validate_order(
            ticker="AAPL", price=100.0,
            capital=10_000.0, open_positions=[]
        )
        assert order.approved
        assert order.qty == 10  # 10% de 10 000 / 100$ = 10 actions

    def test_qty_rounds_down_to_whole_shares(self):
        order = validate_order(
            ticker="AAPL", price=130.0,
            capital=10_000.0, open_positions=[]
        )
        assert order.approved
        assert order.qty == 7  # 1000 / 130 = 7.69 → 7

    def test_qty_is_zero_when_price_exceeds_budget(self):
        order = validate_order(
            ticker="BRK", price=700_000.0,
            capital=10_000.0, open_positions=[]
        )
        assert not order.approved
        assert order.rejection == RejectionReason.INSUFFICIENT_BUDGET


class TestMaxPositions:
    def test_rejected_when_five_positions_already_open(self):
        open_pos = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
        order = validate_order(
            ticker="NVDA", price=100.0,
            capital=50_000.0, open_positions=open_pos
        )
        assert not order.approved
        assert order.rejection == RejectionReason.MAX_POSITIONS_REACHED

    def test_approved_with_four_positions_open(self):
        open_pos = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        order = validate_order(
            ticker="NVDA", price=100.0,
            capital=50_000.0, open_positions=open_pos
        )
        assert order.approved

    def test_rejected_when_ticker_already_open(self):
        order = validate_order(
            ticker="AAPL", price=100.0,
            capital=50_000.0, open_positions=["AAPL"]
        )
        assert not order.approved
        assert order.rejection == RejectionReason.ALREADY_OPEN


class TestStopLoss:
    def test_stop_price_is_5_percent_below_entry(self):
        order = validate_order(
            ticker="AAPL", price=200.0,
            capital=10_000.0, open_positions=[]
        )
        assert order.approved
        assert order.stop_price == pytest.approx(190.0, rel=1e-3)
