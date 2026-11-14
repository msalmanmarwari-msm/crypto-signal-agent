"""Walk-forward backtest: strategy ka real win-rate check karta hai.

Usage:
    python scripts/backtest.py --days 30
    python scripts/backtest.py --days 30 --symbols DOGEUSDT,ADAUSDT
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from agent import data, indicators, journal, strategy  # noqa: E402
from agent.config import ENTRY_INTERVAL, TREND_INTERVAL, load_settings  # noqa: E402
from agent.outcomes import simulate  # noqa: E402
from agent.risk import build_plan  # noqa: E402

DAY_MS = 86_400_000


def backtest_symbol(symbol: str, days: int, settings, btc1h, max_hold_bars: int):
    now = int(time.time() * 1000)
    df15 = data.fetch_range(symbol, ENTRY_INTERVAL, now - (days + 8) * DAY_MS, now, max_pages=8, cache=True)
    df1h = data.fetch_range(symbol, TREND_INTERVAL, now - (days + 45) * DAY_MS, now, max_pages=6, cache=True)
    if df15.empty or df1h.empty:
        return []

    df15 = indicators.add_indicators(df15)
    df1h = indicators.add_htf_trend(indicators.add_indicators(df1h))

    eval_end = len(df15) - max_hold_bars
    cooldown_bars = int(settings.cooldown_hours * 4)
    max_hold_ms = settings.max_hold_hours * 3_600_000

    trades = []
    last_signal_i = -10**9
    i = 40
    while i < eval_end:
        if i - last_signal_i < cooldown_bars:
            i += 1
            continue
        dec = strategy.evaluate(symbol, df1h, df15, btc1h, settings, idx15=i)
        if dec is None:
            i += 1
            continue
        plan = build_plan(dec, settings)
        if plan is None:
            i += 1
            continue

        oc = simulate(
            dec.side, dec.entry, plan.stop, plan.tp1, plan.tp2,
            df15.iloc[i + 1 : i + 1 + max_hold_bars],
            entry_ts_ms=dec.candle_close_time_ms,
            max_hold_ms=max_hold_ms,
        )
        trades.append(
            {
                "symbol": symbol,
                "side": dec.side,
                "time": dec.candle_close_time_iso,
                "status": oc.status,
                "r": oc.r,
                "hit_tp1": oc.hit_tp1,
            }
        )
        last_signal_i = i
        i += 1
    return trades


def summarize(trades, label: str):
    wins = sum(1 for t in trades if t["status"] == "WIN")
    losses = sum(1 for t in trades if t["status"] == "LOSS")
    expired = sum(1 for t in trades if t["status"] == "EXPIRED")
    decided = wins + losses
    wr = (wins / decided * 100) if decided else 0.0
    avg_r = (sum(t["r"] for t in trades) / len(trades)) if trades else 0.0
    print(
        f"{label:<12} signals={len(trades):>4}  win={wins:>3}  loss={losses:>3}  "
        f"expired={expired:>3}  win_rate={wr:5.1f}%  avgR={avg_r:+.2f}"
    )
    return wins, decided, avg_r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--symbols", default="")
    args = ap.parse_args()

    settings = load_settings()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or list(settings.symbols)

    print(
        f"Backtest: last {args.days} days | {len(symbols)} symbols | "
        f"min_score={settings.min_score} | cooldown={settings.cooldown_hours:g}h | "
        f"stop>={settings.min_stop_atr:g}ATR"
    )
    print("-" * 96)

    btc1h = None
    try:
        now = int(time.time() * 1000)
        raw = data.fetch_range("BTCUSDT", TREND_INTERVAL, now - (args.days + 45) * DAY_MS, now, max_pages=6, cache=True)
        btc1h = indicators.add_htf_trend(indicators.add_indicators(raw)) if not raw.empty else None
    except data.MarketDataError as exc:
        print(f"WARN: BTC filter data unavailable ({exc})")

    max_hold_bars = int(settings.max_hold_hours * 4)
    all_trades = []
    for sym in symbols:
        try:
            trades = backtest_symbol(sym, args.days, settings, btc1h, max_hold_bars)
        except data.MarketDataError as exc:
            print(f"{sym:<12} ERROR {exc}")
            continue
        summarize(trades, sym)
        all_trades.extend(trades)
        time.sleep(1.0)

    print("-" * 96)
    wins, decided, avg_r = summarize(all_trades, "TOTAL")
    if decided:
        print(f"\nWin rate: {wins / decided * 100:.1f}%  |  Avg R per trade: {avg_r:+.2f}  ({len(all_trades)} signals)")
        longs = sum(1 for t in all_trades if t["side"] == "LONG")
        print(f"LONG: {longs} | SHORT: {len(all_trades) - longs}")
        win_rs = [t["r"] for t in all_trades if t["status"] == "WIN"]
        if win_rs:
            avg_win = sum(win_rs) / len(win_rs)
            print(f"Avg win: {avg_win:+.2f}R  |  Break-even win rate: {1 / (1 + avg_win) * 100:.0f}%")
        print("Note: past data hai, future guarantee nahi. Fees/slippage include nahi.")
    else:
        print("\nKoi trade nahi mila — filters bahut strict hain ya data kam hai.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
