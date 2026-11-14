"""Telegram live chat worker — cloud ke liye.

GitHub Actions par chalta hai: Telegram ko long-poll karta hai aur /setup,
/price, /status, /signals, /news, /add, /stats ka jawab seconds mein bhejta hai.
`--commit` ke saath har batch ke baad state git mein push hoti hai, taake job
band/timeout hone par commands dobara handle na hon.

Laptop par bina --commit chalayein (git push ki zaroorat nahi):
    python scripts/chat_bot.py --minutes 60
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from agent import trade_journal  # noqa: E402
from agent.config import load_settings  # noqa: E402


def _git(*args: str) -> bool:
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip().splitlines()
        print(f"git {args[0]} fail: {detail[-1][:200] if detail else 'unknown'}", flush=True)
    return res.returncode == 0


def _branch() -> str:
    env = os.getenv("GITHUB_REF_NAME", "").strip()
    if env:
        return env
    res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    return res.stdout.strip() or "main"


def commit_state(path: str) -> None:
    if not os.path.exists(path) or not _git("add", path):
        return
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    if not _git("commit", "-m", "chore: update chat state [skip ci]"):
        return
    branch = _branch()
    for attempt in range(3):
        if _git("push", "origin", f"HEAD:{branch}"):
            print("state push ho gayi", flush=True)
            return
        _git("pull", "--rebase", "--autostash", "origin", branch)
        time.sleep(2 * (attempt + 1))
    print("state push fail — agli batch mein retry", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram live chat worker")
    parser.add_argument("--minutes", type=float, default=54.0, help="kitni der chale (default 54)")
    parser.add_argument("--wait", type=int, default=45, help="long-poll seconds (default 45)")
    parser.add_argument("--commit", action="store_true", help="state ko git mein push karein")
    args = parser.parse_args()

    settings = load_settings()
    if settings.dry_run:
        print("DRY_RUN=0 karein warna bot reply nahi karega.")
        return 1
    if not settings.telegram_token or not settings.telegram_chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing.")
        return 1

    on_batch = None
    if args.commit:
        on_batch = lambda: commit_state(settings.trade_journal_path)  # noqa: E731

    total = trade_journal.serve(settings, args.minutes, args.wait, on_batch=on_batch)
    print(f"Worker khatam — {total} command(s) handle hui.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
