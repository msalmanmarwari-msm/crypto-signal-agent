"""Personal profit/loss journal via Telegram commands.

Aap Telegram par messages bhej kar apni trades ka result record kar sakte hain:
    /add LONG DOGE +2.5 TP2 hit
    /list
    /stats
    /del 3
    /help

Data data/trade_journal.json mein save hota hai. Sirf configured
TELEGRAM_CHAT_ID se aaye messages accept hote hain.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone

import requests

from . import notifier
from .config import Settings

log = logging.getLogger(__name__)

API = "https://api.telegram.org"
EMPTY = {"entries": [], "meta": {"next_id": 1, "telegram_offset": 0}}

HELP_TEXT = (
    "📒 Trade Journal — commands\n"
    "━━━━━━━━━━━━━━━━\n"
    "/add LONG DOGE +2.5 TP2 hit\n"
    "  • side: LONG ya SHORT\n"
    "  • coin: DOGE, BTC, ADA...\n"
    "  • result: profit/loss % (+2.5 ya -1)\n"
    "/list — last 10 trades\n"
    "/stats — total, win rate, net %\n"
    "/del 3 — trade #3 delete\n"
    "/help — ye message\n"
    "⚠️ Sirf aap ki chat se commands accept hoti hain."
)


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {"entries": [], "meta": {"next_id": 1, "telegram_offset": 0}}

    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return {"entries": [], "meta": {"next_id": 1, "telegram_offset": 0}}
    data.setdefault("entries", [])
    data.setdefault("meta", {})
    data["meta"].setdefault("next_id", len(data["entries"]) + 1)
    data["meta"].setdefault("telegram_offset", 0)
    return data


def save(path: str, data: dict) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_command(text: str) -> tuple[str, list[str]]:
    text = (text or "").strip()
    if not text.startswith("/"):
        return "", []
    parts = text.split()
    return parts[0].split("@")[0].lower(), parts[1:]


def _parse_pct(raw: str) -> float | None:
    cleaned = raw.replace("%", "").replace("+", "").replace("R", "").replace("r", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def stats_text(data: dict) -> str:
    entries = data["entries"]
    if not entries:
        return "📒 Journal khali hai. `/add LONG DOGE +2.5` se shuru karein."

    results = [float(e["result_pct"]) for e in entries]
    wins = [r for r in results if r > 0]
    losses = [r for r in results if r < 0]
    decided = len(wins) + len(losses)
    net = sum(results)
    win_rate = len(wins) / decided * 100 if decided else 0.0
    avg = net / len(results)

    return (
        "📒 Trade Journal\n"
        f"Trades: {len(entries)} | Win: {len(wins)} | Loss: {len(losses)}\n"
        f"Net: {net:+.2f}% | Avg: {avg:+.2f}%\n"
        f"Win rate: {win_rate:.1f}%\n"
        f"Best: {max(results):+.2f}% | Worst: {min(results):+.2f}%"
    )


def list_text(data: dict, last: int = 10) -> str:
    entries = data["entries"][-last:]
    if not entries:
        return "📒 Journal khali hai."

    lines = [f"📒 Last {len(entries)} trade(s)"]
    for e in reversed(entries):
        day = e["date"][:10]
        note = f" | {e['note']}" if e.get("note") else ""
        lines.append(f"#{e['id']} {day} {e['side']} {e['symbol']} {e['result_pct']:+.2f}%{note}")
    return "\n".join(lines)


def add_entry(data: dict, side: str, symbol: str, result_pct: float, note: str) -> dict:
    entry = {
        "id": int(data["meta"]["next_id"]),
        "date": _now_iso(),
        "side": side,
        "symbol": symbol,
        "result_pct": round(result_pct, 2),
        "note": note.strip(),
    }
    data["entries"].append(entry)
    data["meta"]["next_id"] = entry["id"] + 1
    return entry


def handle_command(cmd: str, args: list[str], data: dict) -> str:
    if cmd in ("/start", "/help"):
        return HELP_TEXT

    if cmd == "/add":
        if len(args) < 3:
            return "❌ Format: `/add LONG DOGE +2.5 TP2 hit`"

        side = args[0].upper()
        side = {"L": "LONG", "BUY": "LONG", "S": "SHORT", "SELL": "SHORT"}.get(side, side)
        if side not in ("LONG", "SHORT"):
            return "❌ Side LONG ya SHORT hona chahiye."

        symbol = args[1].upper().replace("USDT", "").strip()
        if not symbol:
            return "❌ Coin ka naam likhein (jaise DOGE)."

        result = _parse_pct(args[2])
        if result is None:
            return "❌ Result % number hona chahiye, jaise +2.5 ya -1.2"

        entry = add_entry(data, side, symbol, result, " ".join(args[3:]))
        st = stats_text(data)
        return (
            f"✅ Trade add ho gaya #{entry['id']}: {side} {symbol} {result:+.2f}%\n"
            f"━━━━━━━━━━━━━━━━\n{st}"
        )

    if cmd == "/list":
        return list_text(data)

    if cmd == "/stats":
        return stats_text(data)

    if cmd == "/del":
        if not args:
            return "❌ Format: `/del 3`"
        try:
            entry_id = int(args[0].lstrip("#"))
        except ValueError:
            return "❌ Trade id number hona chahiye."

        for idx, entry in enumerate(data["entries"]):
            if entry["id"] == entry_id:
                data["entries"].pop(idx)
                return f"🗑️ Trade #{entry_id} delete ho gaya."

        return f"❌ Trade #{entry_id} nahi mila."

    return "❓ Command samajh nahi aayi. `/help` bhejein."


def _fetch_updates(token: str, offset: int, wait_seconds: int) -> list[dict]:
    params: dict = {"timeout": wait_seconds, "allowed_updates": '["message"]'}
    if offset:
        params["offset"] = offset
    resp = requests.get(
        f"{API}/bot{token}/getUpdates",
        params=params,
        timeout=wait_seconds + 15,
    )
    body = resp.json()
    if not body.get("ok"):
        log.warning("Telegram getUpdates error: %s", str(body)[:200])
        return []
    return body.get("result", [])


def poll(settings: Settings, wait_seconds: int = 0) -> int:
    """Naye Telegram commands process karta hai. Return: kitne commands handle hue."""
    if settings.dry_run or not settings.telegram_token or not settings.telegram_chat_id:
        return 0

    data = load(settings.trade_journal_path)
    offset = int(data["meta"].get("telegram_offset") or 0)

    try:
        updates = _fetch_updates(settings.telegram_token, offset, wait_seconds)
    except (requests.RequestException, ValueError) as exc:
        log.warning("Telegram polling fail: %s", exc)
        return 0

    handled = 0
    changed = False
    for upd in updates:
        offset = max(offset, int(upd.get("update_id", 0)) + 1)
        changed = True
        msg = upd.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        if chat_id != str(settings.telegram_chat_id):
            log.info("Unknown chat %s se message ignore hua", chat_id)
            continue

        cmd, args = parse_command(msg.get("text", ""))
        if not cmd:
            continue

        reply = handle_command(cmd, args, data)
        if notifier.send_text(reply, settings):
            handled += 1
        if cmd in ("/add", "/del"):
            save(settings.trade_journal_path, data)

    if changed:
        data["meta"]["telegram_offset"] = offset
        save(settings.trade_journal_path, data)
    return handled
