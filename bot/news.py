from dataclasses import dataclass
import yfinance as yf

IMPACT_THRESHOLD = 5

KEYWORDS: dict[str, int] = {
    "earnings": 3, "EPS": 3, "revenue": 2, "profit": 2, "beat": 3, "miss": 3,
    "guidance": 3, "outlook": 2, "forecast": 2, "raise": 2, "cut": 2,
    "upgrade": 4, "downgrade": 4, "outperform": 3, "underperform": 3,
    "overweight": 3, "underweight": 3,
    "price target": 2, "target": 1,
    "merger": 4, "acquisition": 4, "buyout": 4, "deal": 2, "spinoff": 3,
    "dividend": 2, "buyback": 2, "split": 2,
    "layoff": 3, "layoffs": 3, "restructuring": 3,
    "FDA": 4, "approval": 3, "rejected": 4, "recall": 4,
    "SEC": 3, "investigation": 4, "lawsuit": 3, "fine": 3, "fraud": 4,
    "recession": 3, "GDP": 2,
    "surge": 2, "plunge": 3, "crash": 4, "soar": 2, "all-time": 3,
}

NOISE_PATTERNS = [
    "week in review", "bestseller list", "top ten",
    "fight night", "odds, lines",
]


@dataclass
class NewsItem:
    headline:    str
    score:       int
    high_impact: bool


def _is_noise(headline: str) -> bool:
    hl = headline.lower()
    return any(p in hl for p in NOISE_PATTERNS)


def _score(headline: str) -> int:
    hl = headline.lower()
    return sum(w for kw, w in KEYWORDS.items() if kw.lower() in hl)


def _fetch_yfinance(ticker: str) -> list[str]:
    news = yf.Ticker(ticker).news
    return [
        n.get("content", {}).get("title", "")
        for n in news
        if n.get("content", {}).get("title")
    ]


def classify_news(ticker: str, headlines: list[str] | None = None) -> list[NewsItem]:
    if headlines is None:
        headlines = _fetch_yfinance(ticker)

    items = []
    for h in headlines:
        if not h or _is_noise(h):
            continue
        score = _score(h)
        items.append(NewsItem(headline=h, score=score, high_impact=score >= IMPACT_THRESHOLD))
    return items
