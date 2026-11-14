from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from . import data, journal
from .config import ENTRY_INTERVAL, Settings
from .outcomes import simulate

log = logging.getLogger(__name__)


def _iso(ms: int | None) -> str:
    ts = ms if ms is not None else int(time.time() * 1000)
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def update_open_signals(data_journal: dict, settings: Settings, now_ms: int | None = None) -> int:
    now = int(time.time() * 1000) if now_ms is None else now_ms
    updated = 0

    for sig in journal.open_signals(data_journal):
        start = int(sig["entry_time_ms"]) + 1
        try:
            df = data.fetch_range(sig["symbol"], ENTRY_INTERVAL, start, now, max_pages=4)
        except data.MarketDataError as exc:
            log.warning("tracker fetch failed for %s: %s", sig["symbol"], exc)
            continue
        if df.empty:
            continue

        oc = simulate(
            sig["side"],
            float(sig["entry"]),
            float(sig["stop"]),
            float(sig["tp1"]),
            float(sig["tp2"]),
            df,
            entry_ts_ms=int(sig["entry_time_ms"]),
            max_hold_ms=int(settings.max_hold_hours * 3_600_000),
        )
        sig["hit_tp1"] = oc.hit_tp1
        if oc.hit_tp1:
            sig["hit_tp2"] = oc.reason == "TP2 hit"

        if oc.closed:
            sig["status"] = oc.status
            sig["outcome_r"] = oc.r
            sig["close_reason"] = oc.reason
            sig["closed_at"] = _iso(oc.exit_ts_ms)
            updated += 1
            log.info(
                "tracked %s %s -> %s (%s, %+.2fR)",
                sig["symbol"], sig["side"], oc.status, oc.reason, oc.r,
            )
        else:
            sig["unrealized_r"] = oc.r

    return updated
