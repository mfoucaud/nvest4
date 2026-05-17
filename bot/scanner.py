from dataclasses import dataclass, field
import pandas as pd
import pandas_ta as ta
import yfinance as yf

RSI_OVERSOLD    = 35
RSI_OVERBOUGHT  = 65
VOLUME_SPIKE_MX = 1.5
LOOKBACK_DAYS   = 20  # fenêtre pour la moyenne volume


@dataclass
class SignalResult:
    ticker:        str
    close:         float
    rsi:           float | None
    signals:       list[str] = field(default_factory=list)
    passes_filter: bool = False


def fetch_ohlcv(ticker: str) -> pd.DataFrame | None:
    df = yf.download(ticker, period="60d", interval="1d", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or len(df) < 22:
        return None
    return df


def compute_signals(df: pd.DataFrame, ticker: str) -> SignalResult:
    df = df.copy()
    df.ta.rsi(length=14, append=True)
    df.ta.ema(length=9,  append=True)
    df.ta.ema(length=21, append=True)

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    rsi    = latest.get("RSI_14")
    ema9   = latest.get("EMA_9")
    ema21  = latest.get("EMA_21")
    p_ema9 = prev.get("EMA_9")
    p_ema21= prev.get("EMA_21")

    volume  = float(latest["Volume"])
    avg_vol = float(df["Volume"].iloc[-LOOKBACK_DAYS - 1:-1].mean())
    close   = float(latest["Close"])

    signals = []

    if rsi is not None:
        if rsi < RSI_OVERSOLD:
            signals.append(f"RSI_OVERSOLD({rsi:.1f})")
        elif rsi > RSI_OVERBOUGHT:
            signals.append(f"RSI_OVERBOUGHT({rsi:.1f})")

    if all(v is not None for v in [ema9, ema21, p_ema9, p_ema21]):
        if p_ema9 < p_ema21 and ema9 > ema21:
            signals.append("EMA_CROSS_UP")
        elif p_ema9 > p_ema21 and ema9 < ema21:
            signals.append("EMA_CROSS_DOWN")

    if avg_vol > 0 and volume > avg_vol * VOLUME_SPIKE_MX:
        signals.append(f"VOL_SPIKE({volume / avg_vol:.1f}x)")

    return SignalResult(
        ticker=ticker,
        close=close,
        rsi=float(rsi) if rsi is not None else None,
        signals=signals,
        passes_filter=len(signals) > 0,
    )


def scan_watchlist(tickers: list[str]) -> list[SignalResult]:
    results = []
    for ticker in tickers:
        df = fetch_ohlcv(ticker)
        if df is None:
            continue
        result = compute_signals(df, ticker)
        if result.passes_filter:
            results.append(result)
    return results
