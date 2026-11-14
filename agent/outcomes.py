from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Outcome:
    status: str  # WIN / LOSS / EXPIRED
    r: float
    reason: str
    hit_tp1: bool
    exit_ts_ms: int | None
    closed: bool


def simulate(
    side: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    df: pd.DataFrame,
    entry_ts_ms: int | None = None,
    max_hold_ms: int | None = None,
) -> Outcome:
    """Conservative walk-forward: 50% book TP1 par, baaki TP2 tak, SL pehle TP1 ke baad breakeven.

    Same candle mein SL aur TP dono ho to SL maana jata hai (worst case).
    """
    risk = abs(entry - stop)
    if risk <= 0 or df is None or df.empty:
        return Outcome("EXPIRED", 0.0, "invalid data", False, None, False)

    hit_tp1 = False
    be_stop = stop
    last_close = float(df["close"].iloc[-1])
    last_ts = int(df["close_time"].iloc[-1])

    for row in df.itertuples(index=False):
        high, low, close = float(row.high), float(row.low), float(row.close)
        ts = int(row.close_time)

        if max_hold_ms is not None and entry_ts_ms is not None and ts - entry_ts_ms > max_hold_ms:
            move = (close - entry) if side == "LONG" else (entry - close)
            r = (0.5 + 0.5 * move / risk) if hit_tp1 else move / risk
            return Outcome("EXPIRED", round(r, 3), "time exit", hit_tp1, ts, True)

        if side == "LONG":
            if not hit_tp1:
                if low <= stop:
                    return Outcome("LOSS", -1.0, "stop hit", False, ts, True)
                if high >= tp1:
                    hit_tp1 = True
                    be_stop = entry
            else:
                if low <= be_stop:
                    return Outcome("WIN", 0.5, "TP1 + breakeven", True, ts, True)
                if high >= tp2:
                    return Outcome("WIN", 1.5, "TP2 hit", True, ts, True)
        else:
            if not hit_tp1:
                if high >= stop:
                    return Outcome("LOSS", -1.0, "stop hit", False, ts, True)
                if low <= tp1:
                    hit_tp1 = True
                    be_stop = entry
            else:
                if high >= be_stop:
                    return Outcome("WIN", 0.5, "TP1 + breakeven", True, ts, True)
                if low <= tp2:
                    return Outcome("WIN", 1.5, "TP2 hit", True, ts, True)

    move = (last_close - entry) if side == "LONG" else (entry - last_close)
    r = (0.5 + 0.5 * move / risk) if hit_tp1 else move / risk
    return Outcome("EXPIRED", round(r, 3), "data ended", hit_tp1, last_ts, False)
