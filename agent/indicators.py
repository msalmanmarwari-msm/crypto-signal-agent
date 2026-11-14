from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    out = out.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return out


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(series, fast) - ema(series, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig, line - sig


def add_htf_trend(df1h: pd.DataFrame, hours: int = 4) -> pd.DataFrame:
    """Higher-timeframe trend: 1h candles se 4h resample, EMA50/EMA200 regime.

    Sirf last *completed* 4h candle ka regime use hota hai (no lookahead).
    Column: h4_trend = 1 up, -1 down, 0 chop.
    """
    out = df1h.copy()
    bucket_ms = hours * 3_600_000
    bucket = out["open_time"] // bucket_ms

    close = out.groupby(bucket)["close"].last()
    fast = close.ewm(span=50, adjust=False, min_periods=50).mean()
    slow = close.ewm(span=200, adjust=False, min_periods=200).mean()

    regime = pd.Series(0, index=close.index)
    regime[(fast > slow) & (close > fast)] = 1
    regime[(fast < slow) & (close < slow)] = -1

    out["h4_trend"] = bucket.map(regime.shift(1)).fillna(0).astype(int)
    return out


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = out["close"]

    out["ema20"] = ema(close, 20)
    out["ema50"] = ema(close, 50)
    out["ema200"] = ema(close, 200)
    out["rsi"] = rsi(close, 14)

    macd_line, macd_sig, macd_hist = macd(close)
    out["macd"] = macd_line
    out["macd_sig"] = macd_sig
    out["macd_hist"] = macd_hist

    out["atr"] = atr(out, 14)
    out["atr_pct"] = out["atr"] / close * 100.0

    out["vol_ma20"] = sma(out["volume"], 20)
    out["vol_ratio"] = out["volume"] / out["vol_ma20"].replace(0.0, np.nan)

    out["swing_low20"] = out["low"].rolling(20).min().shift(1)
    out["swing_high20"] = out["high"].rolling(20).max().shift(1)
    return out
