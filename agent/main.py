from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone

from . import data, journal, news, notifier, tracker, trade_journal
from .market import fetch_prepared
from .config import ENTRY_INTERVAL, TREND_INTERVAL, Settings, load_settings
from .risk import build_plan
from .strategy import evaluate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agent")

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SUMMARY_WEEKDAY = 0  # Monday (0=Mon)


def run(settings: Settings) -> int:
    now_ms = int(time.time() * 1000)

    if not settings.dry_run and (not settings.telegram_token or not settings.telegram_chat_id):
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing. .env ya GitHub secrets set karein.")
        return 1

    jrnl = journal.load(settings.journal_path)

    try:
        if settings.telegram_poll:
            handled = trade_journal.poll(settings)
            if handled:
                log.info("Trade journal: %d Telegram command(s) handle hui", handled)
    except Exception:
        log.exception("Trade journal polling fail — scan par asar nahi")

    tracked = tracker.update_open_signals(jrnl, settings, now_ms)
    if tracked:
        log.info("Updated %d existing signal(s)", tracked)

    btc1h = None
    if settings.btc_filter:
        try:
            btc1h = fetch_prepared("BTCUSDT", TREND_INTERVAL)
            log.info("BTC 1h candles: %d", len(btc1h))
        except data.MarketDataError as exc:
            log.warning("BTC filter data unavailable, continuing without it: %s", exc)

    sent = 0
    scanned = 0
    skipped = 0
    candidates: list[tuple] = []

    daily_left = settings.max_signals_per_day - journal.signals_today(jrnl, now_ms)
    if daily_left <= 0:
        log.info("Daily signal cap reached (%d)", settings.max_signals_per_day)

    for symbol in settings.symbols:
        if daily_left <= 0:
            break

        if journal.has_recent(jrnl, symbol, settings.cooldown_hours, now_ms):
            log.info("%s: cooldown yaa open signal hai, skip", symbol)
            continue

        try:
            df1h = fetch_prepared(symbol, TREND_INTERVAL)
            df15 = fetch_prepared(symbol, ENTRY_INTERVAL)
        except data.MarketDataError as exc:
            log.warning("%s: data fetch failed, skip (%s)", symbol, exc)
            continue

        scanned += 1
        dec = evaluate(symbol, df1h, df15, btc1h, settings)
        if dec is None:
            log.info("%s: koi signal nahi", symbol)
            continue

        plan = build_plan(dec, settings)
        if plan is None:
            skipped += 1
            log.info("%s: %s mila lekin risk filter fail (volatility), skip", symbol, dec.side)
            continue

        if journal.exists(jrnl, f"{dec.symbol}-{dec.candle_close_time_ms}"):
            log.info("%s: duplicate signal, skip", symbol)
            continue

        candidates.append((dec, plan))

    # Best score pehle, aur ek hi direction mein sab signals nahi (correlation guard)
    candidates.sort(key=lambda item: (item[0].score, item[0].confidence), reverse=True)
    side_counts = {"LONG": 0, "SHORT": 0}

    for dec, plan in candidates:
        if sent >= min(settings.max_new_per_run, daily_left):
            break
        if side_counts[dec.side] >= settings.max_per_side_per_run:
            log.info("%s: %s per-run side cap reached, skip", dec.symbol, dec.side)
            continue

        sig = journal.make_signal(dec, plan, settings)
        message = notifier.build_signal_message(sig, settings)
        if notifier.send_text(message, settings):
            journal.add(jrnl, sig)
            side_counts[dec.side] += 1
            sent += 1
            log.info(
                "SIGNAL %s %s @ %s (score %d/%d)", sig["side"], sig["symbol"], sig["entry"], sig["score"], sig["max_score"]
            )
        else:
            log.error("%s: Telegram send fail, signal journal mein save nahi kiya", dec.symbol)

    if settings.news_enabled:
        try:
            if news.maybe_send(settings, jrnl, now_ms):
                log.info("News digest bheja gaya")
        except Exception:
            log.exception("News digest fail — signals par asar nahi")

    now_utc = datetime.now(timezone.utc)
    today = now_utc.strftime("%Y-%m-%d")
    if now_utc.weekday() == SUMMARY_WEEKDAY and now_utc.hour == 0 and not journal.summary_sent_today(jrnl, today):
        if notifier.send_text("📈 Weekly check-in\n\n" + journal.stats_text(jrnl), settings):
            journal.mark_summary_sent(jrnl, today)

    jrnl["meta"]["last_run"] = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    jrnl["meta"]["last_run_sent"] = sent
    journal.save(settings.journal_path, jrnl)

    st = journal.stats(jrnl)
    log.info(
        "Run complete: scanned=%d sent=%d skipped=%d | closed=%d win_rate=%.1f%% avgR=%+.2f",
        scanned, sent, skipped, st["closed"], st["win_rate"], st["avg_r"],
    )
    return 0


def main() -> int:
    settings = load_settings()
    log.info("Symbols: %s", ", ".join(settings.symbols))
    try:
        return run(settings)
    except KeyboardInterrupt:
        return 130
    except Exception:
        log.exception("Agent crashed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
