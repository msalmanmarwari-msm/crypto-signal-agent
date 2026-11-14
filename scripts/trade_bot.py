"""Telegram trade-journal bot — instant replies (long polling).

Ye script laptop par chalti rehti hai to /add, /stats etc. ka jawab foran aata hai.
GitHub Actions wala run bhi har 15 min par commands process karta hai, lekin usme
reply thodi der se aata hai. Dono saath na chalayein (offset share hota hai).

Usage:
    python scripts/trade_bot.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from agent import trade_journal  # noqa: E402
from agent.config import load_settings  # noqa: E402


def main() -> int:
    settings = load_settings()
    if settings.dry_run:
        print("DRY_RUN=0 karein warna bot Telegram par reply nahi karega.")
        return 1
    if not settings.telegram_token or not settings.telegram_chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing.")
        return 1

    print("📒 Trade journal bot chalu. Telegram par /help bhejein. Ctrl+C se band.")
    while True:
        try:
            handled = trade_journal.poll(settings, wait_seconds=25)
        except KeyboardInterrupt:
            print("\nBot band ho gaya.")
            return 0
        except Exception as exc:  # network blips par crash na ho
            print("error:", exc)
            time.sleep(5)
        else:
            if handled:
                print(f"{handled} command(s) handled")


if __name__ == "__main__":
    sys.exit(main())
