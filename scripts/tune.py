"""Parameter tuning + out-of-sample validation.

Data ek dafa fetch hota hai, phir multiple configs test hote hain.
Pehla half = in-sample (tune), doosra half = out-of-sample (honest check).

Usage:
    python scripts/tune.py --days 45
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from agent import data, indicators, strategy  # noqa: E402
from agent.config import ENTRY_INTERVAL, TREND_INTERVAL, load_settings  # noqa: E402
from agent.outcomes import simulate  # noqa: E402
from agent.risk import build_plan  # noqa: E402

DAY_MS = 86_400_000

VARIANTS = [
    # (min_score, mmc_filter, mmc_min_points, cooldown_hours, btc_strict, htf_filter,
    #  qfl, qb, qfl_require, ccp, ros)
    (8, True, 1, 4, False, True, True, True, True, True, False),   # final default (QFL require)
    (8, True, 1, 4, False, True, True, True, False, True, False),  # purana default (core gate)
    (8, True, 1, 4, False, True, True, True, True, True, True),    # + ROS room
    (8, True, 1, 4, True, True, True, True, True, True, False),    # + BTC strict
    (7, True, 1, 4, False, True, True, True, True, True, False),   # min_score 7
    (9, True, 1, 4, False, True, True, True, True, True, False),   # min_score 9
]


def load_dataset(settings, symbols, days):
    now = int(time.time() * 1000)
    out = {}
    for sym in symbols:
        try:
            df15 = data.fetch_range(sym, ENTRY_INTERVAL, now - (days + 8) * DAY_MS, now, max_pages=10, cache=True)
            df1h = data.fetch_range(sym, TREND_INTERVAL, now - (days + 45) * DAY_MS, now, max_pages=6, cache=True)
        except data.MarketDataError as exc:
            print(f"skip {sym}: {exc}")
            continue
        if df15.empty or df1h.empty:
            continue
        out[sym] = (indicators.add_indicators(df15), indicators.add_htf_trend(indicators.add_indicators(df1h)))
    btc1h = None
    try:
        raw = data.fetch_range("BTCUSDT", TREND_INTERVAL, now - (days + 45) * DAY_MS, now, max_pages=6, cache=True)
        btc1h = indicators.add_htf_trend(indicators.add_indicators(raw)) if not raw.empty else None
    except data.MarketDataError as exc:
        print(f"BTC filter unavailable: {exc}")
    return out, btc1h


def run_config(settings, dataset, btc1h, mid_ts):
    max_hold_bars = int(settings.max_hold_hours * 4)
    max_hold_ms = settings.max_hold_hours * 3_600_000
    cooldown_bars = int(settings.cooldown_hours * 4)
    is_trades, oos_trades = [], []

    for sym, (df15, df1h) in dataset.items():
        eval_end = len(df15) - max_hold_bars
        last_i = -10**9
        for i in range(40, eval_end):
            if i - last_i < cooldown_bars:
                continue
            dec = strategy.evaluate(sym, df1h, df15, btc1h, settings, idx15=i)
            if dec is None:
                continue
            plan = build_plan(dec, settings)
            if plan is None:
                continue
            oc = simulate(
                dec.side, dec.entry, plan.stop, plan.tp1, plan.tp2,
                df15.iloc[i + 1 : i + 1 + max_hold_bars],
                entry_ts_ms=dec.candle_close_time_ms, max_hold_ms=max_hold_ms,
            )
            trade = (oc.status, oc.r, dec.side)
            (is_trades if dec.candle_close_time_ms < mid_ts else oos_trades).append(trade)
            last_i = i
    return is_trades, oos_trades


def ratio(trades):
    wins = sum(1 for t in trades if t[0] == "WIN")
    losses = sum(1 for t in trades if t[0] == "LOSS")
    decided = wins + losses
    wr = wins / decided * 100 if decided else 0.0
    avg_r = sum(t[1] for t in trades) / len(trades) if trades else 0.0
    return wr, avg_r, decided


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--symbols", default="")
    args = ap.parse_args()

    base = load_settings()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or list(base.symbols)
    print(f"Loading {len(symbols)} symbols x {args.days} days...")
    dataset, btc1h = load_dataset(base, symbols, args.days)
    if not dataset:
        print("No data")
        return 1

    first = next(iter(dataset.values()))[0]
    mid_ts = int(first["close_time"].iloc[len(first) // 2])
    print(f"Bars per symbol: {len(first)} | train/OOS split at candle {len(first) // 2}")

    print(
        f"\n{'score':>5} {'mmcPts':>6} {'strict':>6} {'htf':>5} {'req':>4} {'ccp':>4} {'ros':>4} | "
        f"{'signals':>7} {'trainWR':>8} {'oosWR':>7} {'expR':>6}"
    )
    print("-" * 100)
    rows = []
    for min_score, mmc_on, mmc_pts, cooldown, strict, htf, qfl, qb, require, ccp, ros in VARIANTS:
        cfg = dataclasses.replace(
            base,
            min_score=min_score,
            mmc_filter=mmc_on,
            mmc_min_points=mmc_pts or base.mmc_min_points,
            cooldown_hours=cooldown,
            btc_strict=strict,
            htf_filter=htf,
            qfl_filter=qfl,
            qb_filter=qb,
            qfl_require=require,
            ccp_filter=ccp,
            ros_filter=ros,
        )
        is_trades, oos_trades = run_config(cfg, dataset, btc1h, mid_ts)
        wr_is, r_is, n_is = ratio(is_trades)
        wr_oos, r_oos, n_oos = ratio(oos_trades)
        exp_r = (r_is * n_is + r_oos * n_oos) / max(1, n_is + n_oos)
        rows.append(
            (min_score, mmc_pts, strict, htf, require, ccp, ros, n_is + n_oos, wr_is, wr_oos, exp_r)
        )

    for min_score, mmc_pts, strict, htf, require, ccp, ros, n, wr_is, wr_oos, exp_r in sorted(
        rows, key=lambda x: (x[9], x[10]), reverse=True
    ):
        print(
            f"{min_score:>5} {mmc_pts:>6} {str(strict):>6} {str(htf):>5} {str(require):>4} "
            f"{str(ccp):>4} {str(ros):>4} | "
            f"{n:>7} {wr_is:>7.1f}% {wr_oos:>6.1f}% {exp_r:>+6.2f}"
        )
    print("\nNote: OOS column par focus karein (overfitting pakadne ke liye). 30+ signals hon tabhi bharosa karein.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
