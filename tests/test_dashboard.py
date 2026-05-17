from bot.dashboard import render_dashboard


def _position(ticker="AAPL", entry=150.0, current=160.0, qty=5, reasoning="RSI oversold"):
    return {
        "ticker":    ticker,
        "entry":     entry,
        "current":   current,
        "qty":       qty,
        "pnl":       (current - entry) * qty,
        "reasoning": reasoning,
    }


def _analysis(ticker="AAPL", action="BUY", reasoning="Strong signal", traded=True):
    return {
        "ticker":    ticker,
        "action":    action,
        "reasoning": reasoning,
        "traded":    traded,
        "timestamp": "2026-05-17T10:00:00",
    }


class TestRenderDashboard:
    def test_returns_html_string(self):
        html = render_dashboard(positions=[], analyses=[], portfolio={})
        assert isinstance(html, str)
        assert "<html" in html.lower()

    def test_includes_ticker_in_positions(self):
        html = render_dashboard(
            positions=[_position("NVDA")],
            analyses=[],
            portfolio={"capital": 10_000, "pnl": 500, "win_rate": 0.6, "trades": 3},
        )
        assert "NVDA" in html

    def test_includes_pnl_value(self):
        html = render_dashboard(
            positions=[_position("AAPL", entry=100.0, current=110.0, qty=10)],
            analyses=[],
            portfolio={},
        )
        assert "100" in html  # P&L = (110-100)*10 = 100

    def test_includes_reasoning_in_positions(self):
        html = render_dashboard(
            positions=[_position(reasoning="Volume spike on earnings day")],
            analyses=[],
            portfolio={},
        )
        assert "Volume spike on earnings day" in html

    def test_includes_analysis_history(self):
        html = render_dashboard(
            positions=[],
            analyses=[_analysis("TSLA", action="HOLD", reasoning="Pas de signal clair")],
            portfolio={},
        )
        assert "TSLA" in html
        assert "HOLD" in html

    def test_includes_portfolio_kpis(self):
        html = render_dashboard(
            positions=[],
            analyses=[],
            portfolio={"capital": 12_500, "pnl": 1_250, "win_rate": 0.75, "trades": 8},
        )
        assert "12" in html   # capital
        assert "75" in html   # win_rate %

    def test_empty_positions_renders_without_error(self):
        html = render_dashboard(positions=[], analyses=[], portfolio={})
        assert html  # non vide
