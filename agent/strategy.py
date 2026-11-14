from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import mmc
from .config import Settings, WARMUP_1H

MAX_CORE_SCORE = 9


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%d %b %Y, %H:%M UTC")


@dataclass
class Decision:
    symbol: str
    side: str
    score: int
    max_score: int
    confidence: int
    reasons: list[str]
    entry: float
    atr15: float
    rsi15: float
    vol_ratio: float
    swing_low: float
    swing_high: float
    candle_close_time_ms: int
    candle_close_time_iso: str


class _Cols:
    """Fast scalar access into a prepared DataFrame (numpy arrays, cached per frame)."""

    __slots__ = ("arrays",)

    def __init__(self, df: pd.DataFrame):
        self.arrays = {name: df[name].to_numpy() for name in df.columns}

    def get(self, row: int, name: str) -> float:
        arr = self.arrays.get(name)
        if arr is None or row < 0 or row >= arr.shape[0]:
            return math.nan
        return float(arr[row])


_CACHE_ATTR = "_agent_cols"


def _cols(df: pd.DataFrame) -> _Cols:
    cache = df.attrs.get(_CACHE_ATTR)
    if cache is None:
        cache = _Cols(df)
        df.attrs[_CACHE_ATTR] = cache
    return cache


def _asof(c: _Cols, ts_ms: int) -> int:
    return int(np.searchsorted(c.arrays["close_time"], ts_ms, side="right") - 1)


def _ok(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


def _btc_regime(c: _Cols, b: int) -> int:
    ema50, ema200, close = c.get(b, "ema50"), c.get(b, "ema200"), c.get(b, "close")
    if not _ok(ema50, ema200, close):
        return 0
    if ema50 > ema200 and close > ema200:
        return 1
    if ema50 < ema200 and close < ema200:
        return -1
    return 0


@dataclass
class Analysis:
    """Poora hisaab — evaluate() isi se signal banata hai, bot isi se jawab deta hai."""

    symbol: str
    side: str
    score: int
    max_score: int
    reasons: list[str]
    gates: list[tuple[str, bool]]
    block: str | None
    long_score: int
    short_score: int
    entry: float
    atr15: float
    atr_pct: float
    rsi15: float
    rsi1h: float
    vol_ratio: float
    h4_trend: float
    btc_regime: int
    swing_low: float
    swing_high: float
    candle_close_time_ms: int
    candle_close_time_iso: str
    mmc_points: int = 0
    mmc_core: int = 0
    has_qfl: bool = False
    has_qb: bool = False
    has_ccp: bool = False
    has_room: bool = True
    qfl_line: float | None = None
    box_lo: float | None = None
    box_hi: float | None = None


def analyze_symbol(
    symbol: str,
    df1h: pd.DataFrame,
    df15: pd.DataFrame,
    btc1h: pd.DataFrame | None,
    settings: Settings,
    idx15: int | None = None,
    full: bool = False,
) -> Analysis | None:
    if df15 is None or df1h is None or len(df15) < 60 or len(df1h) < WARMUP_1H:
        return None

    i = len(df15) - 1 if idx15 is None else int(idx15)
    if i < 40 or i >= len(df15):
        return None

    c15, c1h = _cols(df15), _cols(df1h)

    close_ts = c15.get(i, "close_time")
    if not math.isfinite(close_ts):
        return None
    j = _asof(c1h, int(close_ts))
    if j < WARMUP_1H - 1:
        return None

    close = c15.get(i, "close")
    atr15 = c15.get(i, "atr")
    ema20 = c15.get(i, "ema20")
    rsi15 = c15.get(i, "rsi")
    hist = c15.get(i, "macd_hist")
    hist_prev = c15.get(i - 1, "macd_hist")
    vol_ratio = c15.get(i, "vol_ratio")
    swing_low = c15.get(i, "swing_low20")
    swing_high = c15.get(i, "swing_high20")

    if not _ok(close, atr15, ema20, rsi15, hist, hist_prev, swing_low, swing_high):
        return None
    if close <= 0 or atr15 <= 0:
        return None
    if not math.isfinite(vol_ratio):
        vol_ratio = 1.0

    atr_pct = atr15 / close * 100.0
    atr_ok = settings.atr_min_pct <= atr_pct <= settings.atr_max_pct

    past = c15.get(i - 3, "close")
    chase_ok = not (math.isfinite(past) and past > 0 and abs(close - past) > 3.5 * atr15)

    ema50_1h = c1h.get(j, "ema50")
    ema200_1h = c1h.get(j, "ema200")
    close_1h = c1h.get(j, "close")
    ema50_prev = c1h.get(j - 10, "ema50")
    rsi1h = c1h.get(j, "rsi")
    if not _ok(ema50_1h, ema200_1h, close_1h, ema50_prev, rsi1h):
        return None

    trend_up = ema50_1h > ema200_1h and close_1h > ema50_1h and ema50_1h > ema50_prev
    trend_down = ema50_1h < ema200_1h and close_1h < ema50_1h and ema50_1h < ema50_prev

    btc_regime = 0
    if settings.btc_filter and btc1h is not None and len(btc1h) > WARMUP_1H:
        btc_cols = _cols(btc1h)
        b = _asof(btc_cols, int(close_ts))
        if b >= WARMUP_1H - 1:
            btc_regime = _btc_regime(btc_cols, b)

    touched_up = touched_dn = False
    for k in range(max(0, i - 2), i + 1):
        if c15.get(k, "low") <= ema20 * 1.001:
            touched_up = True
        if c15.get(k, "high") >= ema20 * 0.999:
            touched_dn = True
    reclaimed_up = close > ema20 and touched_up
    reclaimed_dn = close < ema20 and touched_dn

    long_score = 0
    short_score = 0
    long_reasons: list[str] = []
    short_reasons: list[str] = []

    if trend_up:
        long_score += 2
        long_reasons.append("1h uptrend: EMA50 > EMA200 aur price EMA50 ke upar")
    if trend_down:
        short_score += 2
        short_reasons.append("1h downtrend: EMA50 < EMA200 aur price EMA50 ke neeche")

    if 45 <= rsi1h <= 72:
        long_score += 1
        long_reasons.append(f"1h RSI healthy uptrend zone mein ({rsi1h:.0f})")
    if 28 <= rsi1h <= 55:
        short_score += 1
        short_reasons.append(f"1h RSI healthy downtrend zone mein ({rsi1h:.0f})")

    if hist > 0:
        long_score += 1
        long_reasons.append("15m MACD histogram positive")
    if hist < 0:
        short_score += 1
        short_reasons.append("15m MACD histogram negative")

    if hist > hist_prev:
        long_score += 1
        long_reasons.append("15m MACD momentum upar")
    if hist < hist_prev:
        short_score += 1
        short_reasons.append("15m MACD momentum neeche")

    if 45 <= rsi15 <= 68:
        long_score += 1
        long_reasons.append(f"15m RSI 45-68 entry zone ({rsi15:.0f})")
    if 32 <= rsi15 <= 55:
        short_score += 1
        short_reasons.append(f"15m RSI 32-55 entry zone ({rsi15:.0f})")

    if vol_ratio >= settings.vol_mult:
        long_score += 1
        short_score += 1
        long_reasons.append(f"Volume average ka {vol_ratio:.1f}x")
        short_reasons.append(f"Volume average ka {vol_ratio:.1f}x")

    if reclaimed_up:
        long_score += 1
        long_reasons.append("15m pullback hokar EMA20 reclaim hua")
    if reclaimed_dn:
        short_score += 1
        short_reasons.append("15m rally hokar EMA20 se reject hua")

    if btc_regime >= 0:
        long_score += 1
        long_reasons.append("BTC 1h bearish nahi hai")
    if btc_regime <= 0:
        short_score += 1
        short_reasons.append("BTC 1h bullish nahi hai")

    side = "LONG" if long_score >= short_score else "SHORT"
    score = long_score if side == "LONG" else short_score
    reasons = list(long_reasons if side == "LONG" else short_reasons)

    core_ok = score >= settings.min_score

    # MMC mehnga hai — evaluate() mein sirf tab chalta hai jab tak pichle
    # gates pass hon (backtest speed). Bot (full=True) hamesha chalta hai.
    mres = None
    if settings.mmc_filter and (full or (atr_ok and chase_ok and core_ok)):
        mres = mmc.analyze(
            c15,
            c1h,
            i,
            j,
            side,
            close,
            qfl=settings.qfl_filter,
            qb=settings.qb_filter,
            ccp=settings.ccp_filter,
        )

    mmc_core = mres.core_points if mres else 0
    if mres is not None:
        score += mres.points
        reasons = reasons + mres.reasons

    h4_trend = c1h.get(j, "h4_trend")
    if not math.isfinite(h4_trend):
        h4_trend = 0.0

    gates: list[tuple[str, bool]] = [
        (f"ATR% {settings.atr_min_pct:g}-{settings.atr_max_pct:g}% range", atr_ok),
        ("anti-chase (3 candle move < 3.5 ATR)", chase_ok),
        (f"core score >= {settings.min_score}", core_ok),
    ]
    if settings.mmc_filter:
        gates.append((f"MMC core points >= {settings.mmc_min_points}", mmc_core >= settings.mmc_min_points))
        if settings.qfl_require:
            gates.append(("QFL/QB structure par price", bool(mres and (mres.has_qfl or mres.has_qb))))
        if settings.ros_filter:
            gates.append(("aage room (opposite swing door nahi)", bool(mres and mres.has_room)))
    if settings.htf_filter:
        gates.append(("4h trend same direction", h4_trend == (1 if side == "LONG" else -1)))
    gates.append(("BTC against nahi", btc_regime <= 0 if side == "SHORT" else btc_regime >= 0))
    if settings.btc_strict:
        gates.append(("BTC strict alignment", btc_regime == (-1 if side == "SHORT" else 1)))
    gates.append(("RSI15 extreme nahi", rsi15 >= 25 if side == "SHORT" else rsi15 <= 75))

    block = next((label for label, passed in gates if not passed), None)
    if block is None and settings.htf_filter:
        reasons.append("4h trend same direction mein hai")

    qfl_line = box_lo = box_hi = None
    if full:
        zone = mmc._origin_zone(c15, i, side)
        if zone is not None:
            qfl_line, box_lo, box_hi = zone[0], zone[1], zone[2]

    return Analysis(
        symbol=symbol.upper(),
        side=side,
        score=score,
        max_score=MAX_CORE_SCORE + (mmc.MAX_MMC_POINTS if settings.mmc_filter else 0),
        reasons=reasons,
        gates=gates,
        block=block,
        long_score=long_score,
        short_score=short_score,
        entry=close,
        atr15=atr15,
        atr_pct=atr_pct,
        rsi15=rsi15,
        rsi1h=rsi1h,
        vol_ratio=vol_ratio,
        h4_trend=h4_trend,
        btc_regime=btc_regime,
        swing_low=swing_low,
        swing_high=swing_high,
        candle_close_time_ms=int(close_ts),
        candle_close_time_iso=_iso(int(close_ts)),
        mmc_points=mres.points if mres else 0,
        mmc_core=mmc_core,
        has_qfl=bool(mres and mres.has_qfl),
        has_qb=bool(mres and mres.has_qb),
        has_ccp=bool(mres and mres.has_ccp),
        has_room=bool(mres.has_room) if mres else True,
        qfl_line=qfl_line,
        box_lo=box_lo,
        box_hi=box_hi,
    )


def to_decision(a: Analysis) -> Decision:
    return Decision(
        symbol=a.symbol,
        side=a.side,
        score=a.score,
        max_score=a.max_score,
        confidence=int(round(a.score / a.max_score * 100)),
        reasons=a.reasons,
        entry=a.entry,
        atr15=a.atr15,
        rsi15=a.rsi15,
        vol_ratio=a.vol_ratio,
        swing_low=a.swing_low,
        swing_high=a.swing_high,
        candle_close_time_ms=a.candle_close_time_ms,
        candle_close_time_iso=a.candle_close_time_iso,
    )


def evaluate(
    symbol: str,
    df1h: pd.DataFrame,
    df15: pd.DataFrame,
    btc1h: pd.DataFrame | None,
    settings: Settings,
    idx15: int | None = None,
) -> Decision | None:
    a = analyze_symbol(symbol, df1h, df15, btc1h, settings, idx15=idx15)
    if a is None or a.block is not None:
        return None
    return to_decision(a)
