from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

from .config import Settings

EMPTY = {"signals": [], "meta": {}}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: str) -> dict:
    if not os.path.exists(path):
        return json.loads(json.dumps(EMPTY))
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return json.loads(json.dumps(EMPTY))
    data.setdefault("signals", [])
    data.setdefault("meta", {})
    return data


def save(path: str, data: dict) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def exists(data: dict, signal_id: str) -> bool:
    return any(s["id"] == signal_id for s in data["signals"])


def add(data: dict, signal: dict) -> None:
    data["signals"].append(signal)
    data["meta"]["last_signal_at"] = signal["created_at"]


def open_signals(data: dict) -> list[dict]:
    return [s for s in data["signals"] if s.get("status") == "OPEN"]


def has_recent(data: dict, symbol: str, hours: float, now_ms: int) -> bool:
    cutoff = now_ms - int(hours * 3600 * 1000)
    for sig in data["signals"]:
        if sig["symbol"] != symbol:
            continue
        if sig.get("status") == "OPEN":
            return True
        if int(sig.get("entry_time_ms", 0)) >= cutoff:
            return True
    return False


def signals_today(data: dict, now_ms: int) -> int:
    day_start = now_ms - (now_ms % 86_400_000)
    return sum(1 for s in data["signals"] if int(s.get("entry_time_ms", 0)) >= day_start)


def stats(data: dict, last_n: int | None = None) -> dict:
    closed = [s for s in data["signals"] if s.get("status") in ("WIN", "LOSS", "EXPIRED")]
    closed.sort(key=lambda s: s.get("closed_at", ""))
    if last_n:
        closed = closed[-last_n:]

    wins = [s for s in closed if s["status"] == "WIN"]
    losses = [s for s in closed if s["status"] == "LOSS"]
    expired = [s for s in closed if s["status"] == "EXPIRED"]
    decided = len(wins) + len(losses)
    win_rate = (len(wins) / decided * 100.0) if decided else 0.0
    avg_r = (sum(float(s.get("outcome_r", 0.0)) for s in closed) / len(closed)) if closed else 0.0
    return {
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "expired": len(expired),
        "win_rate": win_rate,
        "avg_r": avg_r,
        "open": len(open_signals(data)),
    }


def stats_text(data: dict, last_n: int | None = None) -> str:
    st = stats(data, last_n)
    scope = f"last {last_n}" if last_n else "all time"
    return (
        f"📊 Performance ({scope})\n"
        f"Closed: {st['closed']} | Win: {st['wins']} | Loss: {st['losses']} | Expired: {st['expired']}\n"
        f"Win rate: {st['win_rate']:.1f}%  |  Avg R: {st['avg_r']:+.2f}R\n"
        f"Open signals: {st['open']}"
    )


def summary_sent_today(data: dict, today: str) -> bool:
    return data["meta"].get("last_summary_date") == today


def mark_summary_sent(data: dict, today: str) -> None:
    data["meta"]["last_summary_date"] = today


def make_signal(dec, plan, settings: Settings) -> dict:
    return {
        "id": f"{dec.symbol}-{dec.candle_close_time_ms}",
        "symbol": dec.symbol,
        "side": dec.side,
        "entry": round(dec.entry, 10),
        "stop": round(plan.stop, 10),
        "tp1": round(plan.tp1, 10),
        "tp2": round(plan.tp2, 10),
        "tp3": round(plan.tp3, 10),
        "risk_pct": round(plan.risk_pct, 3),
        "risk_per_unit": plan.risk_per_unit,
        "qty": plan.qty,
        "score": dec.score,
        "max_score": dec.max_score,
        "confidence": dec.confidence,
        "reasons": list(dec.reasons),
        "rsi15": round(dec.rsi15, 2),
        "vol_ratio": round(dec.vol_ratio, 2),
        "entry_time_ms": dec.candle_close_time_ms,
        "entry_time_iso": dec.candle_close_time_iso,
        "created_at": now_iso(),
        "status": "OPEN",
        "hit_tp1": False,
        "hit_tp2": False,
        "outcome_r": None,
        "closed_at": None,
        "close_reason": None,
    }
