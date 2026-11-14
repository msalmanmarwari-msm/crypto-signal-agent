from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

COIN_NAMES = {
    "TRXUSDT": "TRON (TRX)",
    "DOGEUSDT": "Dogecoin (DOGE)",
    "ADAUSDT": "Cardano (ADA)",
    "XLMUSDT": "Stellar (XLM)",
    "HBARUSDT": "Hedera (HBAR)",
    "CROUSDT": "Cronos (CRO)",
    "SHIBUSDT": "Shiba Inu (SHIB)",
    "PEPEUSDT": "Pepe (PEPE)",
    "DOTUSDT": "Polkadot (DOT)",
    "VETUSDT": "VeChain (VET)",
}

DEFAULT_SYMBOLS = tuple(COIN_NAMES.keys())

TREND_INTERVAL = "1h"
ENTRY_INTERVAL = "15m"
WARMUP_1H = 220


def _f(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Env var {name} must be a number, got {raw!r}") from exc


def _i(name: str, default: int) -> int:
    return int(_f(name, float(default)))


def _b(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    telegram_chat_id: str
    symbols: tuple[str, ...]

    equity_usdt: float
    risk_per_trade_pct: float

    min_score: int
    max_signals_per_day: int
    max_new_per_run: int
    max_per_side_per_run: int
    cooldown_hours: float
    min_risk_pct: float
    max_risk_pct: float
    max_hold_hours: float

    atr_min_pct: float
    atr_max_pct: float
    vol_mult: float
    stop_pad_atr: float
    min_stop_atr: float

    mmc_filter: bool
    mmc_min_points: int
    qfl_filter: bool
    qb_filter: bool
    qfl_require: bool
    ccp_filter: bool
    ros_filter: bool

    htf_filter: bool

    news_enabled: bool
    news_interval_hours: float
    news_lookback_hours: float
    news_max_crypto: int
    news_max_macro: int

    btc_filter: bool
    btc_strict: bool
    telegram_poll: bool
    dry_run: bool
    journal_path: str
    trade_journal_path: str


def load_settings() -> Settings:
    raw_symbols = os.getenv("SYMBOLS", "").strip()
    symbols = (
        tuple(s.strip().upper() for s in raw_symbols.split(",") if s.strip())
        if raw_symbols
        else DEFAULT_SYMBOLS
    )
    qfl_filter = _b("QFL_FILTER", True)
    qb_filter = _b("QB_FILTER", True)
    qfl_require = _b("QFL_REQUIRE", True)
    if qfl_require and not (qfl_filter or qb_filter):
        raise ValueError("QFL_REQUIRE=1 ke liye QFL_FILTER ya QB_FILTER mein se ek 1 hona chahiye")
    return Settings(
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        symbols=symbols,
        equity_usdt=_f("EQUITY_USDT", 100.0),
        risk_per_trade_pct=_f("RISK_PER_TRADE_PCT", 1.0),
        min_score=_i("MIN_SCORE", 8),
        max_signals_per_day=_i("MAX_SIGNALS_PER_DAY", 6),
        max_new_per_run=_i("MAX_NEW_PER_RUN", 2),
        max_per_side_per_run=_i("MAX_PER_SIDE_PER_RUN", 2),
        cooldown_hours=_f("COOLDOWN_HOURS", 4.0),
        min_risk_pct=_f("MIN_RISK_PCT", 0.5),
        max_risk_pct=_f("MAX_RISK_PCT", 3.0),
        max_hold_hours=_f("MAX_HOLD_HOURS", 72.0),
        atr_min_pct=_f("ATR_MIN_PCT", 0.25),
        atr_max_pct=_f("ATR_MAX_PCT", 3.0),
        vol_mult=_f("VOL_MULT", 1.2),
        stop_pad_atr=_f("STOP_PAD_ATR", 0.5),
        min_stop_atr=_f("MIN_STOP_ATR", 1.2),
        mmc_filter=_b("MMC_FILTER", True),
        mmc_min_points=_i("MMC_MIN_POINTS", 1),
        qfl_filter=qfl_filter,
        qb_filter=qb_filter,
        qfl_require=qfl_require,
        ccp_filter=_b("CCP_FILTER", True),
        ros_filter=_b("ROS_FILTER", False),
        htf_filter=_b("HTF_FILTER", True),
        news_enabled=_b("NEWS_ENABLED", True),
        news_interval_hours=_f("NEWS_INTERVAL_HOURS", 1.0),
        news_lookback_hours=_f("NEWS_LOOKBACK_HOURS", 24.0),
        news_max_crypto=_i("NEWS_MAX_CRYPTO", 4),
        news_max_macro=_i("NEWS_MAX_MACRO", 3),
        btc_filter=_b("BTC_FILTER", True),
        btc_strict=_b("BTC_STRICT", False),
        telegram_poll=_b("TELEGRAM_POLL", True),
        dry_run=_b("DRY_RUN", False),
        journal_path=os.getenv("JOURNAL_PATH", "data/journal.json").strip(),
        trade_journal_path=os.getenv("TRADE_JOURNAL_PATH", "data/trade_journal.json").strip(),
    )
