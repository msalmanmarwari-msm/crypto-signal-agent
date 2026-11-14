from __future__ import annotations

import time

from . import news, strategy
from .config import ENTRY_INTERVAL, TREND_INTERVAL, Settings
from .market import fetch_prepared
from .notifier import fmt_price
from .risk import build_plan

COMMANDS = ("/price", "/setup", "/status", "/signals", "/news")

HELP_LIVE = (
    "Live commands:\n"
    "/setup XLM — poora analysis (score, kaunsa rule block kar raha, QFL line)\n"
    "/price XLM — price + 24h change\n"
    "/signals — aaj ke signals aur open trades\n"
    "/status — agent ki halat aur settings\n"
    "/news — abhi taaza news digest"
)


def resolve_symbol(settings: Settings, raw: str) -> str | None:
    key = (raw or "").strip().upper().replace("/", "").replace("-", "")
    if not key:
        return None
    if not key.endswith("USDT"):
        key += "USDT"
    return key if key in settings.symbols else None


def _coin(symbol: str) -> str:
    return symbol.replace("USDT", "")


def price_text(settings: Settings, symbol: str) -> str:
    df = fetch_prepared(symbol, ENTRY_INTERVAL)
    if df.empty or len(df) < 100:
        return f"❌ {_coin(symbol)}: data nahi mila, dobara try karein."

    close = float(df["close"].iloc[-1])
    back = float(df["close"].iloc[-97])
    window = df.iloc[-96:]
    change = (close - back) / back * 100 if back else 0.0
    arrow = "🟢" if change >= 0 else "🔴"
    return (
        f"💰 {_coin(symbol)} (USDT)\n"
        f"Price: {fmt_price(close)}\n"
        f"24h: {arrow} {change:+.2f}%\n"
        f"24h high: {fmt_price(float(window['high'].max()))}\n"
        f"24h low: {fmt_price(float(window['low'].min()))}"
    )


def setup_text(settings: Settings, symbol: str) -> str:
    df15 = fetch_prepared(symbol, ENTRY_INTERVAL)
    df1h = fetch_prepared(symbol, TREND_INTERVAL)
    btc1h = None
    if settings.btc_filter:
        try:
            btc1h = fetch_prepared("BTCUSDT", TREND_INTERVAL)
        except Exception:
            btc1h = None

    a = strategy.analyze_symbol(symbol, df1h, df15, btc1h, settings, full=True)
    if a is None:
        return f"❌ {_coin(symbol)}: data kaafi nahi (naya coin?) — abhi analysis nahi ho sakta."

    side_emoji = "🔴" if a.side == "SHORT" else "🟢"
    lines = [
        f"{side_emoji} {_coin(symbol)} — {a.side} lean",
        f"Price {fmt_price(a.entry)} | ATR {a.atr_pct:.2f}%",
        f"1h RSI {a.rsi1h:.0f} | 15m RSI {a.rsi15:.0f} | Vol {a.vol_ratio:.1f}x",
        f"Score: core {a.long_score if a.side == 'LONG' else a.short_score}/"
        f"{strategy.MAX_CORE_SCORE} + MMC {a.mmc_points} pts",
    ]

    mmc_bits = []
    if a.mmc_core:
        mmc_bits.append(f"core {a.mmc_core}")
    if a.has_qfl:
        mmc_bits.append("QFL ✅")
    if a.has_qb:
        mmc_bits.append("QB ✅")
    if a.has_ccp:
        mmc_bits.append("CcP")
    if a.mmc_points:
        lines.append("MMC: " + ", ".join(mmc_bits))

    if a.qfl_line is not None:
        dist = (a.entry - a.qfl_line) / a.qfl_line * 100
        where = "upar" if dist > 0 else "neeche"
        lines.append(f"QFL line {fmt_price(a.qfl_line)} — price {abs(dist):.2f}% {where}")

    lines.append("")
    if a.block is None:
        lines.append("✅ Saare gates pass — signal eligible.")
        dec = strategy.to_decision(a)
        plan = build_plan(dec, settings)
        if plan is not None:
            lines.append(
                f"Entry {fmt_price(a.entry)} | Stop {fmt_price(plan.stop)} ({plan.risk_pct:.2f}%)\n"
                f"TP1 {fmt_price(plan.tp1)} | TP2 {fmt_price(plan.tp2)} | TP3 {fmt_price(plan.tp3)}"
            )
        else:
            lines.append("⚠️ Risk filter ne rok diya (stop 0.5-3% range mein nahi).")
    else:
        lines.append(f"❌ Rok: {a.block}")
        failed = [label for label, ok in a.gates if not ok]
        if len(failed) > 1:
            lines.append("Baaki fail: " + ", ".join(failed[1:]))

    trend_4h = {1: "bullish", -1: "bearish"}.get(int(a.h4_trend), "neutral")
    btc = {1: "bullish", -1: "bearish"}.get(a.btc_regime, "neutral")
    lines.append(f"4h trend {trend_4h} | BTC 1h {btc}")
    return "\n".join(lines)


def signals_text(jrnl: dict) -> str:
    signals = jrnl.get("signals", [])
    if not signals:
        return "📋 Abhi tak koi signal nahi. Filters strict hain — kuch din khamoshi normal hai."

    open_sigs = [s for s in signals if s.get("status") == "OPEN"]
    lines = ["📋 Signals"]
    if open_sigs:
        lines.append("")
        lines.append("🟡 Open:")
        for s in open_sigs[-5:]:
            lines.append(
                f"• {s['side']} {_coin(s['symbol'])} @ {fmt_price(float(s['entry']))} "
                f"(TP1 {fmt_price(float(s['tp1']))})"
            )
    else:
        lines.append("Open: koi nahi")

    closed = [s for s in signals if s.get("status") in ("WIN", "LOSS", "EXPIRED")]
    if closed:
        lines.append("")
        lines.append("Last closed:")
        for s in closed[-5:][::-1]:
            r = s.get("outcome_r")
            r_txt = f"{r:+.2f}R" if isinstance(r, (int, float)) else "-"
            lines.append(f"• {s['status']} {s['side']} {_coin(s['symbol'])} {r_txt}")

    wins = sum(1 for s in closed if s["status"] == "WIN")
    losses = sum(1 for s in closed if s["status"] == "LOSS")
    decided = wins + losses
    if decided:
        lines.append("")
        lines.append(f"Win rate: {wins / decided * 100:.1f}% ({wins}W / {losses}L)")
    return "\n".join(lines)


def status_text(settings: Settings, jrnl: dict, tdata: dict) -> str:
    meta = jrnl.get("meta", {})
    entries = tdata.get("entries", [])
    results = [float(e.get("result_pct", 0)) for e in entries]
    personal = f"{len(entries)} trades"
    if results:
        personal += f", net {sum(results):+.2f}%"

    return (
        "🤖 AGENT STATUS\n"
        f"Last run: {meta.get('last_run') or 'abhi nahi'}\n"
        f"Last news: {meta.get('last_news_at') or 'abhi nahi'}\n"
        f"Scan: har 15 min | News: har {settings.news_interval_hours:g} ghante\n"
        f"Rules: score {settings.min_score}/9 | MMC {settings.mmc_min_points} pt"
        f"{' | QFL/QB zaroori' if settings.qfl_require else ''}"
        f"{' | 4h filter' if settings.htf_filter else ''}\n"
        f"Signals: {len(jrnl.get('signals', []))} total, "
        f"{sum(1 for s in jrnl.get('signals', []) if s.get('status') == 'OPEN')} open\n"
        f"Personal journal: {personal}"
    )


def news_text(settings: Settings) -> str:
    now_ms = int(time.time() * 1000)
    items = news.collect(settings, now_ms)
    picked = news.select_items(items, settings, set())
    if not picked:
        return "📰 Abhi koi fresh news nahi mili (feeds slow ya sab dikha di gayi)."
    return news.build_digest(picked, now_ms)


def handle(cmd: str, args: list[str], settings: Settings, jrnl: dict, tdata: dict) -> str | None:
    if cmd in ("/price", "/setup"):
        if not args:
            return f"❌ Format: `{cmd} XLM`"
        symbol = resolve_symbol(settings, args[0])
        if symbol is None:
            return f"❌ {args[0]} list mein nahi. Coins: " + ", ".join(_coin(s) for s in settings.symbols)
        try:
            return price_text(settings, symbol) if cmd == "/price" else setup_text(settings, symbol)
        except Exception as exc:
            return f"❌ Data fetch fail ({type(exc).__name__}). Thori der baad try karein."

    if cmd == "/signals":
        return signals_text(jrnl)

    if cmd == "/status":
        return status_text(settings, jrnl, tdata)

    if cmd == "/news":
        try:
            return news_text(settings)
        except Exception as exc:
            return f"❌ News fetch fail ({type(exc).__name__}). Thori der baad try karein."

    return None


def plain_query(settings: Settings, text: str) -> str | None:
    """Bina slash wala message: sirf coin ka naam ho to setup bata do."""
    word = (text or "").strip().upper().rstrip("?!.").strip()
    if not word or " " in word:
        return None
    symbol = resolve_symbol(settings, word)
    if symbol is None:
        return None
    try:
        return setup_text(settings, symbol)
    except Exception:
        return None
