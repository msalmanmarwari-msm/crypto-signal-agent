from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .strategy import Decision


@dataclass
class TradePlan:
    stop: float
    tp1: float
    tp2: float
    tp3: float
    risk_per_unit: float
    risk_pct: float
    qty: float | None


def build_plan(dec: Decision, settings: Settings) -> TradePlan | None:
    entry, atr = dec.entry, dec.atr15
    if entry <= 0 or atr <= 0:
        return None

    if dec.side == "LONG":
        stop = dec.swing_low - settings.stop_pad_atr * atr
        stop = min(stop, entry - settings.min_stop_atr * atr)
        risk = entry - stop
    else:
        stop = dec.swing_high + settings.stop_pad_atr * atr
        stop = max(stop, entry + settings.min_stop_atr * atr)
        risk = stop - entry

    if risk <= 0:
        return None

    risk_pct = risk / entry * 100.0
    if not (settings.min_risk_pct <= risk_pct <= settings.max_risk_pct):
        return None

    if dec.side == "LONG":
        tp1, tp2, tp3 = entry + risk, entry + 2 * risk, entry + 3 * risk
    else:
        tp1, tp2, tp3 = entry - risk, entry - 2 * risk, entry - 3 * risk

    qty = None
    if settings.equity_usdt > 0 and settings.risk_per_trade_pct > 0:
        risk_amount = settings.equity_usdt * settings.risk_per_trade_pct / 100.0
        qty = risk_amount / risk

    return TradePlan(
        stop=stop,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        risk_per_unit=risk,
        risk_pct=risk_pct,
        qty=qty,
    )
