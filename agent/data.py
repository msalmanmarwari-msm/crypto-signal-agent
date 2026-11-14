from __future__ import annotations

import logging
import os
import time

import pandas as pd
import requests

log = logging.getLogger(__name__)

CACHE_DIR = os.getenv("DATA_CACHE_DIR", "data/cache")

BINANCE_HOSTS = (
    "https://data-api.binance.vision",
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api4.binance.com",
)

# MEXC ka spot API Binance-compatible hai. CRO Binance par listed nahi,
# isliye fallback source ke taur par use hota hai.
FALLBACK_HOSTS = ("https://api.mexc.com",)

HOSTS = BINANCE_HOSTS + FALLBACK_HOSTS

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades", "taker_buy_base",
    "taker_buy_quote", "ignore",
]

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-signal-agent/0.1"})

_rate_limited_until = 0.0


class MarketDataError(RuntimeError):
    pass


def _now_ms() -> int:
    return int(time.time() * 1000)


def _retry_after(resp: requests.Response) -> float:
    raw = resp.headers.get("Retry-After", "")
    try:
        wait = float(raw)
    except ValueError:
        wait = 5.0
    return min(max(wait, 1.0), 20.0)


def _respect_rate_limit() -> None:
    global _rate_limited_until
    remaining = _rate_limited_until - time.time()
    if remaining > 0:
        time.sleep(min(remaining, 20.0))


def _interval_for(host: str, interval: str) -> str:
    # MEXC hourly interval ko "60m" kehta hai, "1h" ko invalid symbol samajhta hai.
    if host in FALLBACK_HOSTS and interval == "1h":
        return "60m"
    return interval


def _parse(raw: list) -> pd.DataFrame:
    cols = KLINE_COLUMNS[: len(raw[0])]
    df = pd.DataFrame(raw, columns=cols)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = df["open_time"].astype("int64")
    df["close_time"] = df["close_time"].astype("int64")
    return df[["open_time", "open", "high", "low", "close", "volume", "close_time"]]


def fetch_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    start_time: int | None = None,
    end_time: int | None = None,
    drop_unclosed: bool = True,
) -> pd.DataFrame:
    global _rate_limited_until
    params = {"symbol": symbol.upper(), "interval": interval, "limit": int(limit)}
    if start_time is not None:
        params["startTime"] = int(start_time)
    if end_time is not None:
        params["endTime"] = int(end_time)

    last_err = "unknown error"
    invalid_on_binance = False

    for host in HOSTS:
        if invalid_on_binance and host in BINANCE_HOSTS:
            continue
        host_params = dict(params, interval=_interval_for(host, interval))
        for attempt in range(2):
            _respect_rate_limit()
            try:
                resp = _session.get(f"{host}/api/v3/klines", params=host_params, timeout=20)
                if resp.status_code in (429, 418):
                    wait = _retry_after(resp)
                    _rate_limited_until = time.time() + wait
                    last_err = f"rate limited ({resp.status_code})"
                    if attempt == 0:
                        time.sleep(wait)
                        continue
                    break
                if resp.status_code == 400 and "-1121" in resp.text:
                    last_err = f"symbol {symbol} not listed on {host}"
                    if host in BINANCE_HOSTS:
                        invalid_on_binance = True
                    break
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:160]}"
                    break
                data = resp.json()
                if not isinstance(data, list) or not data:
                    last_err = "empty response"
                    break
                df = _parse(data)
                if drop_unclosed:
                    df = df[df["close_time"] <= _now_ms()].reset_index(drop=True)
                if host in FALLBACK_HOSTS:
                    log.info("%s %s: data source %s", symbol, interval, host)
                return df
            except (requests.RequestException, ValueError, KeyError) as exc:
                last_err = str(exc)
                time.sleep(1.0)
        log.debug("host %s failed for %s %s: %s", host, symbol, interval, last_err)

    raise MarketDataError(f"data unavailable for {symbol} {interval}: {last_err}")


def fetch_range(
    symbol: str,
    interval: str,
    start_time: int,
    end_time: int | None = None,
    max_pages: int = 5,
    cache: bool = False,
) -> pd.DataFrame:
    cache_path = None
    if cache:
        end_bucket = int((end_time or _now_ms()) / 86_400_000)
        cache_path = os.path.join(
            CACHE_DIR, f"{symbol.upper()}_{interval}_{int(start_time) // 86_400_000}_{end_bucket}.csv"
        )
        if os.path.exists(cache_path):
            df = pd.read_csv(cache_path)
            for col in ("open_time", "close_time"):
                df[col] = df[col].astype("int64")
            return df

    frames: list[pd.DataFrame] = []
    cursor = int(start_time)
    for _ in range(max_pages):
        batch = fetch_klines(symbol, interval, limit=1000, start_time=cursor, end_time=end_time)
        if batch.empty:
            break
        frames.append(batch)
        next_cursor = int(batch["open_time"].iloc[-1]) + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if end_time is not None and cursor >= int(end_time):
            break
    if not frames:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume", "close_time"])
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
    if end_time is not None:
        df = df[df["close_time"] <= int(end_time)].reset_index(drop=True)
    if cache_path and not df.empty:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_csv(cache_path, index=False)
    return df
