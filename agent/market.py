from __future__ import annotations

import time

import pandas as pd

from . import data, indicators
from .config import ENTRY_INTERVAL, TREND_INTERVAL

HTF_LIMIT = 1000
LTF_LIMIT = 400
HTF_HISTORY_DAYS = 75  # 4h EMA200 ke liye ~33 din chahiye


def fetch_prepared(symbol: str, interval: str, limit: int = 0) -> pd.DataFrame:
    if interval == TREND_INTERVAL:
        now = int(time.time() * 1000)
        # MEXC 500 candles per request deta hai, isliye range-fetch zaroori hai.
        df = data.fetch_range(symbol, interval, now - HTF_HISTORY_DAYS * 86_400_000, now, max_pages=6)
    else:
        df = data.fetch_klines(symbol, interval, limit=limit or LTF_LIMIT, drop_unclosed=True)
    if df.empty:
        return df
    df = indicators.add_indicators(df)
    if interval == TREND_INTERVAL:
        df = indicators.add_htf_trend(df)
    return df
