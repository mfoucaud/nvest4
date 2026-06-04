from bot.dashboard import render_dashboard


def _position(ticker="AAPL", entry=150.0, current=160.0, qty=5, reasoning="RSI oversold", stop_price=None):
    return {
        "ticker":     ticker,
        "entry":      entry,
        "current":    current,
        "qty":        qty,
        "pnl":        (current - entry) * qty,
        "pnl_pct":    (current - entry) / entry * 100,
        "stop_price": stop_price,
        "reasoning":  reasoning,
    }


def _closed(ticker="AAPL", entry=150.0, exit_=160.0, qty=5, reasoning="", timestamp=""):
    return {
        "ticker":    ticker,
        "entry":     entry,
        "exit":      exit_,
        "qty":       qty,
        "pnl":       (exit_ - entry) * qty,
        "reasoning": reasoning,
        "timestamp": timestamp,
    }



class TestRenderDashboard:
    def test_returns_html_string(self):
        html = render_dashboard(positions=[], closed_trades=[], analyses=[], portfolio={})
        assert isinstance(html, str)
        assert "<html" in html.lower()

    def test_includes_ticker_in_positions(self):
        html = render_dashboard(
            positions=[_position("NVDA")],
            closed_trades=[],
            analyses=[],
            portfolio={"capital": 10_000, "pnl": 500, "win_rate": 60, "trades": 3},
        )
        assert "NVDA" in html

    def test_includes_stop_price(self):
        html = render_dashboard(
            positions=[_position("TSLA", stop_price=320.50)],
            closed_trades=[],
            analyses=[],
            portfolio={},
        )
        assert "320.50" in html

    def test_includes_pnl_value(self):
        html = render_dashboard(
            positions=[_position("AAPL", entry=100.0, current=110.0, qty=10)],
            closed_trades=[],
            analyses=[],
            portfolio={},
        )
        assert "100" in html  # P&L = (110-100)*10 = 100

    def test_closed_trade_win_badge(self):
        html = render_dashboard(
            positions=[],
            closed_trades=[_closed("AAPL", entry=100.0, exit_=120.0, qty=5)],
            analyses=[],
            portfolio={},
        )
        assert "GAGNANT" in html

    def test_closed_trade_loss_badge(self):
        html = render_dashboard(
            positions=[],
            closed_trades=[_closed("MSFT", entry=200.0, exit_=180.0, qty=3)],
            analyses=[],
            portfolio={},
        )
        assert "PERDANT" in html

    def test_closed_trade_perf_explanation(self):
        html = render_dashboard(
            positions=[],
            closed_trades=[_closed("NVDA", entry=100.0, exit_=130.0, qty=2, reasoning="RSI signal")],
            analyses=[],
            portfolio={},
        )
        assert "RSI signal" in html

    def test_includes_portfolio_kpis(self):
        html = render_dashboard(
            positions=[],
            closed_trades=[],
            analyses=[],
            portfolio={"capital": 12_500, "pnl": 1_250, "win_rate": 75, "trades": 8},
        )
        assert "12" in html   # capital
        assert "75" in html   # win_rate %

    def test_empty_positions_renders_without_error(self):
        html = render_dashboard(positions=[], closed_trades=[], analyses=[], portfolio={})
        assert html  # non vide
