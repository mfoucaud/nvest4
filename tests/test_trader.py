import pytest
from unittest.mock import MagicMock, call, patch
from bot.trader import execute_order, TradeResult


def _mock_client(buy_status="filled"):
    client = MagicMock()

    buy_order = MagicMock()
    buy_order.id = "buy-123"
    buy_order.status = buy_status

    stop_order = MagicMock()
    stop_order.id = "stop-456"
    stop_order.status = "accepted"

    client.submit_order.side_effect = [buy_order, stop_order]
    client.get_order_by_id.return_value = buy_order

    return client, buy_order, stop_order


class TestExecuteOrder:
    def test_returns_buy_and_stop_ids_on_success(self):
        client, _, _ = _mock_client(buy_status="filled")
        result = execute_order(client, ticker="AAPL", qty=5, trail_percent=5.0)

        assert result.success
        assert result.buy_id == "buy-123"
        assert result.stop_id == "stop-456"

    def test_places_buy_then_stop_in_order(self):
        client, _, _ = _mock_client(buy_status="filled")
        execute_order(client, ticker="AAPL", qty=5, trail_percent=5.0)

        calls = client.submit_order.call_args_list
        assert len(calls) == 2

    def test_cancels_buy_and_raises_on_timeout(self):
        client, buy_order, _ = _mock_client(buy_status="accepted")
        buy_order.status = "accepted"  # jamais filled

        with patch("bot.trader.time.sleep"), pytest.raises(TimeoutError) as exc:
            execute_order(client, ticker="AAPL", qty=5, trail_percent=5.0, poll_timeout=2)

        client.cancel_order_by_id.assert_called_once_with("buy-123")
        assert "AAPL" in str(exc.value)

    def test_stop_not_placed_before_fill(self):
        client, buy_order, _ = _mock_client(buy_status="accepted")

        with patch("bot.trader.time.sleep"), pytest.raises(TimeoutError):
            execute_order(client, ticker="AAPL", qty=5, trail_percent=5.0, poll_timeout=2)

        assert client.submit_order.call_count == 1  # seulement le BUY

    def test_result_carries_ticker(self):
        client, _, _ = _mock_client(buy_status="filled")
        result = execute_order(client, ticker="NVDA", qty=3, trail_percent=5.0)
        assert result.ticker == "NVDA"
