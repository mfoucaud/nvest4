import pytest
from unittest.mock import patch
from bot.news import classify_news, NewsItem


def _raw_article(title: str) -> dict:
    return {"content": {"title": title}}


class TestClassifyNews:
    def test_analyst_upgrade_is_high_impact(self):
        items = classify_news("NVDA", headlines=[
            "Wells Fargo Upgrades NVIDIA Price Target to $200"
        ])
        assert len(items) == 1
        assert items[0].high_impact

    def test_neutral_headline_is_low_impact(self):
        items = classify_news("AAPL", headlines=[
            "Apple releases new color options for iPhone"
        ])
        assert len(items) == 1
        assert not items[0].high_impact

    def test_earnings_beat_is_high_impact(self):
        items = classify_news("MSFT", headlines=[
            "Microsoft Earnings Beat Expectations, Raises Guidance"
        ])
        assert items[0].high_impact

    def test_irrelevant_headline_filtered_out(self):
        items = classify_news("JPM", headlines=[
            "JPMorgan Cuts Advance Auto Parts Price Target"  # JPM = analyste, pas sujet
        ])
        # On vérifie que l'article est retourné mais annoté, pas filtré silencieusement
        assert len(items) == 1

    def test_none_title_is_skipped(self):
        items = classify_news("AAPL", headlines=[None, "Apple stock surges on earnings beat"])
        assert len(items) == 1

    def test_noise_headline_is_skipped(self):
        items = classify_news("AAPL", headlines=[
            "MarketBeat Week in Review – 05/11 - 05/15",
            "Apple beats earnings estimates"
        ])
        assert len(items) == 1
        assert items[0].high_impact

    def test_item_carries_headline_and_score(self):
        items = classify_news("NVDA", headlines=[
            "Wells Fargo Upgrades NVIDIA and Raises Price Target"
        ])
        assert items[0].headline is not None
        assert items[0].score > 0

    def test_fetch_from_yfinance_when_no_headlines_provided(self):
        raw = [_raw_article("Goldman Sachs Downgrades NVIDIA and Cuts Price Target")]
        with patch("bot.news.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.news = raw
            items = classify_news("NVDA")
        assert len(items) == 1
        assert items[0].high_impact
