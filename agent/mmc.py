"""MMC (Mirror Market Concept) layer.

MMC ke core ideas ko objective, testable detectors mein toda gaya hai:
  - BOS / CHoCH (fresh structure break) — sabse strong edge
  - FVG (unfilled imbalance ka rebalance)
  - liquidity sweep / stop-hunt
  - premium / discount (1h dealing range mein price ki position)
  - QFL (Quantity Following Line) — origin line ka retest + hold
  - QB (Quantity Box) — usi origin zone ke andar se entry
  - CcP (complex candle pattern) — engulfing / strong rejection candle
  - ROS room check — opposite 1h swing itna paas na ho ke trade ko jagah na mile

30 din ke backtest par measure hua: structure break (WR 70.1%) aur FVG (73.5%)
baseline (63.3%) se kaafi behtar nikle, isliye signal ke liye in dono mein se
kam se kam ek zaroori hai. Displacement candle aur order block ka koi edge
nahi mila, isliye wo score se hata diye gaye hain.

Points (max 10): structure 3, FVG 2, sweep 1, premium/discount 1, QFL 1, QB 1, CcP 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MAX_MMC_POINTS = 10


@dataclass
class MMCResult:
    points: int
    reasons: list[str]
    has_structure: bool
    has_fvg: bool
    range_pos: float
    has_qfl: bool = False
    has_qb: bool = False
    core_points: int = 0
    has_ccp: bool = False
    has_room: bool = True


def _nan_to(x: float, fallback: float = math.nan) -> float:
    return x if math.isfinite(x) else fallback


def _structure_break(c, i: int, side: str, prior: int = 20, fresh: int = 3) -> bool:
    """BOS/CHoCH: last 3 candles mein purane swing level ka fresh break."""
    open_ = c.arrays["open"]
    high = c.arrays["high"]
    low = c.arrays["low"]

    p_end = i - fresh + 1
    p_start = max(0, p_end - prior)
    if p_end - p_start < 5:
        return False

    if side == "LONG":
        prior_high = float(np.max(high[p_start:p_end]))
        for k in range(p_end, i + 1):
            if high[k] > prior_high and open_[k] <= prior_high:
                return True
    else:
        prior_low = float(np.min(low[p_start:p_end]))
        for k in range(p_end, i + 1):
            if low[k] < prior_low and open_[k] >= prior_low:
                return True
    return False


def _fvg(c, i: int, side: str, lookback: int = 10) -> bool:
    """Fair Value Gap: unfilled imbalance jismein price wapas aa raha hai."""
    high = c.arrays["high"]
    low = c.arrays["low"]
    close = c.arrays["close"]

    for k in range(i - 1, max(i - lookback, 1), -1):
        if side == "LONG":
            gap_bottom, gap_top = high[k - 2], low[k]
            if gap_top <= gap_bottom:
                continue
            if k + 1 <= i - 1 and float(np.min(low[k + 1 : i])) <= gap_bottom:
                continue
            if low[i] <= gap_top and close[i] >= gap_bottom:
                return True
        else:
            gap_top, gap_bottom = low[k - 2], high[k]
            if gap_top <= gap_bottom:
                continue
            if k + 1 <= i - 1 and float(np.max(high[k + 1 : i])) >= gap_top:
                continue
            if high[i] >= gap_bottom and close[i] <= gap_top:
                return True
    return False


def _sweep(c, i: int, side: str, lookback: int = 4) -> bool:
    """Liquidity sweep: swing extreme ke paar wick, close wapas range mein."""
    low = c.arrays["low"]
    high = c.arrays["high"]
    close = c.arrays["close"]

    for k in range(max(0, i - lookback + 1), i + 1):
        if side == "LONG":
            level = _nan_to(c.get(k, "swing_low20"))
            if math.isfinite(level) and low[k] < level and close[k] > level:
                return True
        else:
            level = _nan_to(c.get(k, "swing_high20"))
            if math.isfinite(level) and high[k] > level and close[k] < level:
                return True
    return False


def _origin_zone(c, i: int, side: str, lookback: int = 15, impulse_atr: float = 1.5, base_atr: float = 1.2):
    """QFL/QB ka origin: chhoti base candle ke baad direction mein bada impulse.

    Return: (qfl, box_lo, box_hi, leg_end) ya None.
    """
    high = c.arrays["high"]
    low = c.arrays["low"]
    close = c.arrays["close"]
    atr = c.arrays.get("atr")
    if atr is None:
        return None

    for b in range(i - 4, max(1, i - lookback) - 1, -1):
        a = float(atr[b])
        if not math.isfinite(a) or a <= 0:
            continue
        if float(high[b] - low[b]) > base_atr * a:
            continue  # base candle chhoti honi chahiye
        end = min(b + 3, i - 1)
        if end <= b:
            continue
        leg_hi = float(np.max(high[b + 1 : end + 1]))
        leg_lo = float(np.min(low[b + 1 : end + 1]))
        if side == "LONG":
            if leg_hi > float(high[b]) and leg_hi - float(close[b]) >= impulse_atr * a:
                return float(high[b]), float(low[b]), float(high[b]), end
        else:
            if leg_lo < float(low[b]) and float(close[b]) - leg_lo >= impulse_atr * a:
                return float(low[b]), float(low[b]), float(high[b]), end
    return None


def _qfl_qb(c, i: int, side: str):
    """QFL = origin line ka retest + hold. QB = usi zone ke andar deeper entry."""
    zone = _origin_zone(c, i, side)
    if zone is None:
        return False, False

    qfl, box_lo, box_hi, leg_end = zone
    high = c.arrays["high"]
    low = c.arrays["low"]
    close = c.arrays["close"]
    a = _nan_to(float(c.arrays["atr"][i]))
    if not math.isfinite(a) or a <= 0:
        return False, False
    tol = 0.25 * a

    for k in range(leg_end + 1, i):
        if side == "LONG" and float(close[k]) < box_lo - 0.5 * a:
            return False, False
        if side == "SHORT" and float(close[k]) > box_hi + 0.5 * a:
            return False, False

    if side == "LONG":
        qfl_ok = float(low[i]) <= qfl + tol and float(close[i]) >= qfl
        qb_ok = qfl_ok and float(low[i]) <= qfl - tol and float(low[i]) >= box_lo - 0.5 * a
    else:
        qfl_ok = float(high[i]) >= qfl - tol and float(close[i]) <= qfl
        qb_ok = qfl_ok and float(high[i]) >= qfl + tol and float(high[i]) <= box_hi + 0.5 * a
    return qfl_ok, qb_ok


def _ccp(c, i: int, side: str) -> bool:
    """CcP: engulfing ya strong direction candle (close range ke kinare par)."""
    open_ = c.arrays["open"]
    high = c.arrays["high"]
    low = c.arrays["low"]
    close = c.arrays["close"]

    o, h, l, cl = float(open_[i]), float(high[i]), float(low[i]), float(close[i])
    rng = h - l
    if not math.isfinite(rng) or rng <= 0 or abs(cl - o) < 0.5 * rng:
        return False

    prev_o = float(open_[i - 1])
    prev_c = float(close[i - 1])

    if side == "LONG":
        engulf = cl > max(prev_o, prev_c) and o < min(prev_o, prev_c)
        return bool(cl > o and (engulf or (cl - l) / rng >= 0.7))

    engulf = cl < min(prev_o, prev_c) and o > max(prev_o, prev_c)
    return bool(cl < o and (engulf or (h - cl) / rng >= 0.7))


def _room(c15, c1h, i: int, j: int, side: str, price: float) -> bool:
    """ROS-style room check: opposite 1h swing itna paas na ho ke trade ko jagah na mile."""
    atr15 = _nan_to(c15.get(i, "atr"))
    if not math.isfinite(atr15) or atr15 <= 0:
        return True
    needed = 1.2 * atr15

    start = max(0, j - 24)
    highs = [float(x) for x in c1h.arrays.get("swing_high20", [])[start : j + 1] if math.isfinite(float(x))]
    lows = [float(x) for x in c1h.arrays.get("swing_low20", [])[start : j + 1] if math.isfinite(float(x))]

    if side == "LONG":
        above = [x for x in highs if x > price]
        return (min(above) - price) >= needed if above else True
    below = [x for x in lows if x < price]
    return (price - max(below)) >= needed if below else True


def range_position(c1h, j: int, price: float, length: int = 60) -> float:
    high = c1h.arrays["high"]
    low = c1h.arrays["low"]
    start = max(0, j - length + 1)
    hi = float(np.max(high[start : j + 1]))
    lo = float(np.min(low[start : j + 1]))
    if not math.isfinite(hi) or not math.isfinite(lo) or hi <= lo:
        return 0.5
    return (price - lo) / (hi - lo)


def analyze(
    c15,
    c1h,
    i: int,
    j: int,
    side: str,
    price: float,
    qfl: bool = True,
    qb: bool = True,
    ccp: bool = True,
) -> MMCResult:
    reasons: list[str] = []
    points = 0

    has_structure = _structure_break(c15, i, side)
    if has_structure:
        points += 3
        reasons.append("MMC BOS/CHoCH: 15m structure fresh break")

    has_fvg = _fvg(c15, i, side)
    if has_fvg:
        points += 2
        reasons.append("MMC FVG: imbalance rebalance zone par entry")

    if _sweep(c15, i, side):
        points += 1
        reasons.append("MMC liquidity sweep: stop-hunt ke baad price wapas range mein")

    pos = range_position(c1h, j, price)
    if (side == "LONG" and pos <= 0.5) or (side == "SHORT" and pos >= 0.5):
        points += 1
        zone = "discount" if side == "LONG" else "premium"
        reasons.append(f"MMC {zone} zone: 1h range ka {pos * 100:.0f}% par entry")

    # QFL/QB confirmation points hain, core gate nahi — inke dum par weak
    # setup reject nahi hona chahiye, isliye core_points alag rakha gaya hai.
    core_points = points

    has_qfl = has_qb = False
    if qfl or qb:
        qfl_ok, qb_ok = _qfl_qb(c15, i, side)
        has_qfl = bool(qfl and qfl_ok)
        has_qb = bool(qb and qb_ok)
    if has_qfl:
        points += 1
        reasons.append("MMC QFL: origin line ka retest aur hold")
    if has_qb:
        points += 1
        reasons.append("MMC QB: quantity box ke andar se entry")

    has_ccp = bool(ccp and _ccp(c15, i, side))
    if has_ccp:
        points += 1
        reasons.append("MMC CcP: strong engulfing/rejection candle")

    has_room = _room(c15, c1h, i, j, side, price)

    return MMCResult(
        points=points,
        reasons=reasons,
        has_structure=has_structure,
        has_fvg=has_fvg,
        range_pos=pos,
        has_qfl=has_qfl,
        has_qb=has_qb,
        core_points=core_points,
        has_ccp=has_ccp,
        has_room=has_room,
    )
