from dataclasses import dataclass

import pandas as pd
import yfinance as yf


@dataclass
class MarketRegime:
    regime: str        # "BULL" | "BEAR" | "NEUTRAL"
    spy_perf_5d: float # performance SPY sur 5 jours en %


def fetch_spy() -> pd.DataFrame | None:
    df = yf.download("SPY", period="2y", interval="1d", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or len(df) < 210:
        return None
    return df


def get_market_regime() -> MarketRegime:
    df = fetch_spy()
    if df is None:
        print("[market_regime] SPY fetch failed, defaulting to NEUTRAL")
        return MarketRegime(regime="NEUTRAL", spy_perf_5d=0.0)

    close = df["Close"]
    ema50  = close.ewm(span=50,  adjust=False).mean().iloc[-1]
    ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
    price  = float(close.iloc[-1])

    if price > ema50 > ema200:
        regime = "BULL"
    elif price < ema50 < ema200:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"

    spy_perf_5d = float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100)

    print(f"[market_regime] {regime} | SPY={price:.2f} EMA50={ema50:.2f} EMA200={ema200:.2f} perf5j={spy_perf_5d:+.2f}%")
    return MarketRegime(regime=regime, spy_perf_5d=spy_perf_5d)
