from __future__ import annotations

import logging

import requests

from .config import COIN_NAMES, Settings

log = logging.getLogger(__name__)

API = "https://api.telegram.org"


def fmt_price(p: float) -> str:
    p = float(p)
    if p >= 1000:
        return f"{p:,.2f}"
    if p >= 10:
        return f"{p:,.4f}"
    if p >= 0.1:
        return f"{p:.5f}"
    if p >= 0.001:
        return f"{p:.7f}"
    return f"{p:.9f}".rstrip("0")


def fmt_qty(q: float | None) -> str:
    if not q:
        return "—"
    if q >= 1000:
        return f"{q:,.0f}"
    if q >= 1:
        return f"{q:,.2f}"
    return f"{q:.6f}".rstrip("0")


def build_signal_message(sig: dict, settings: Settings) -> str:
    side = sig["side"]
    head = "🟢 LONG" if side == "LONG" else "🔴 SHORT"
    name = COIN_NAMES.get(sig["symbol"], sig["symbol"])
    entry = float(sig["entry"])
    stop = float(sig["stop"])
    tp1, tp2, tp3 = float(sig["tp1"]), float(sig["tp2"]), float(sig["tp3"])

    stop_pct = (stop - entry) / entry * 100
    qty_line = ""
    if sig.get("qty"):
        risk_usdt = settings.equity_usdt * settings.risk_per_trade_pct / 100
        qty_line = f"\n📦 Size: {fmt_qty(sig['qty'])} {sig['symbol'].replace('USDT', '')}  (risk ~${risk_usdt:.0f})"

    reasons = "\n".join(f"  • {r}" for r in sig.get("reasons", [])[:6])

    return (
        f"{head} — {name}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📍 Entry: {fmt_price(entry)}\n"
        f"🛑 Stop:  {fmt_price(stop)}  ({stop_pct:+.2f}%)\n"
        f"🎯 TP1:   {fmt_price(tp1)}  (1R)\n"
        f"🎯 TP2:   {fmt_price(tp2)}  (2R)\n"
        f"🎯 TP3:   {fmt_price(tp3)}  (3R)"
        f"{qty_line}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🧠 Confidence: {sig['confidence']}%  ({sig['score']}/{sig['max_score']} rules)\n"
        f"📊 15m RSI {sig['rsi15']:.0f} | Volume {sig['vol_ratio']:.1f}x\n"
        f"✅ Reasons:\n{reasons}\n"
        f"🕒 {sig['entry_time_iso']}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⚠️ Sirf {settings.risk_per_trade_pct:g}% capital risk karein, SL zaroor lagayein.\n"
        f"Ye educational signal hai, financial advice nahi.\n"
        f"#{sig['symbol'].replace('USDT', '')} #{side}"
    )


def send_text(text: str, settings: Settings) -> bool:
    if settings.dry_run or not settings.telegram_token or not settings.telegram_chat_id:
        try:
            print("\n" + text + "\n", flush=True)
        except UnicodeEncodeError:
            print("\n" + text.encode("ascii", "replace").decode("ascii") + "\n", flush=True)
        return True

    url = f"{API}/bot{settings.telegram_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=20)
            body = resp.json() if resp.content else {}
            if resp.status_code == 200 and body.get("ok"):
                return True
            log.error("Telegram error %s: %s", resp.status_code, str(body)[:300])
            if resp.status_code in (400, 401, 403, 404):
                return False
        except (requests.RequestException, ValueError) as exc:
            log.error("Telegram request failed (attempt %d): %s", attempt + 1, exc)
    return False
