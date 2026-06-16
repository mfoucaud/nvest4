# bot/scanner.py
from dataclasses import dataclass, field
import pandas as pd
import pandas_ta as ta
import yfinance as yf

RSI_OVERSOLD    = 35
RSI_OVERBOUGHT  = 65
VOLUME_SPIKE_MX = 1.5
LOOKBACK_DAYS   = 20
ADX_MIN         = 25     # force de tendance minimale
MIN_SIGNALS     = 2      # confluence obligatoire


@dataclass
class SignalResult:
    ticker:        str
    close:         float
    rsi:           float | None
    atr:           float
    signals:       list[str] = field(default_factory=list)
    passes_filter: bool = False


def fetch_ohlcv(ticker: str) -> pd.DataFrame | None:
    df = yf.download(ticker, period="60d", interval="1d", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or len(df) < 22:
        return None
    return df


def fetch_ohlcv_1h(ticker: str) -> pd.DataFrame | None:
    df = yf.download(ticker, period="30d", interval="1h", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or len(df) < 21:
        return None
    return df


def _trend_1h(df_1h: pd.DataFrame | None) -> str:
    """Retourne 'UP', 'DOWN' ou 'NEUTRAL' selon EMA9 vs EMA21 sur 1h."""
    if df_1h is None or len(df_1h) < 22:
        return "NEUTRAL"
    df = df_1h.copy()
    df.ta.ema(length=9,  append=True)
    df.ta.ema(length=21, append=True)
    latest = df.iloc[-1]
    ema9  = latest.get("EMA_9")
    ema21 = latest.get("EMA_21")
    if ema9 is None or ema21 is None:
        return "NEUTRAL"
    if ema9 > ema21:
        return "UP"
    if ema9 < ema21:
        return "DOWN"
    return "NEUTRAL"


def compute_signals(df: pd.DataFrame, ticker: str,
                    df_1h: pd.DataFrame | None = None) -> SignalResult:
    df = df.copy()
    df.ta.rsi(length=14, append=True)
    df.ta.ema(length=9,  append=True)
    df.ta.ema(length=21, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.adx(length=14, append=True)
    df.ta.atr(length=14, append=True)

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    rsi    = latest.get("RSI_14")
    ema9   = latest.get("EMA_9")
    ema21  = latest.get("EMA_21")
    p_ema9 = prev.get("EMA_9")
    p_ema21= prev.get("EMA_21")
    macd   = latest.get("MACD_12_26_9")
    macd_s = latest.get("MACDs_12_26_9")
    p_macd = prev.get("MACD_12_26_9")
    p_macd_s = prev.get("MACDs_12_26_9")
    adx    = latest.get("ADX_14")
    atr_val= latest.get("ATRr_14") or latest.get("ATR_14") or 0.0

    volume  = float(latest["Volume"])
    avg_vol = float(df["Volume"].iloc[-LOOKBACK_DAYS - 1:-1].mean())
    close   = float(latest["Close"])

    signals = []

    # RSI
    if rsi is not None:
        if rsi < RSI_OVERSOLD:
            signals.append(f"RSI_OVERSOLD({rsi:.1f})")
        elif rsi > RSI_OVERBOUGHT:
            signals.append(f"RSI_OVERBOUGHT({rsi:.1f})")

    # EMA cross
    if all(v is not None for v in [ema9, ema21, p_ema9, p_ema21]):
        if p_ema9 < p_ema21 and ema9 > ema21:
            signals.append("EMA_CROSS_UP")
        elif p_ema9 > p_ema21 and ema9 < ema21:
            signals.append("EMA_CROSS_DOWN")

    # MACD cross
    if all(v is not None for v in [macd, macd_s, p_macd, p_macd_s]):
        if p_macd < p_macd_s and macd > macd_s:
            signals.append("MACD_CROSS_UP")
        elif p_macd > p_macd_s and macd < macd_s:
            signals.append("MACD_CROSS_DOWN")

    # Volume spike
    if avg_vol > 0 and volume > avg_vol * VOLUME_SPIKE_MX:
        signals.append(f"VOL_SPIKE({volume / avg_vol:.1f}x)")

    # Trend 1h
    trend = _trend_1h(df_1h)
    if trend != "NEUTRAL":
        signals.append(f"TREND_1H_{trend}")

    # Confluence : ≥ MIN_SIGNALS et ADX suffisant
    adx_ok = adx is not None and float(adx) >= ADX_MIN
    passes = len(signals) >= MIN_SIGNALS and adx_ok

    return SignalResult(
        ticker=ticker,
        close=close,
        rsi=float(rsi) if rsi is not None else None,
        atr=float(atr_val),
        signals=signals,
        passes_filter=passes,
    )


def scan_watchlist(tickers: list[str]) -> list[SignalResult]:
    results = []
    for ticker in tickers:
        df = fetch_ohlcv(ticker)
        if df is None:
            continue
        df_1h = fetch_ohlcv_1h(ticker)
        result = compute_signals(df, ticker, df_1h)
        if result.passes_filter:
            results.append(result)
    return results
