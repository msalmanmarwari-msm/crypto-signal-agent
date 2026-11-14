import os
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import trade_journal as tj  # noqa: E402
from agent.config import load_settings  # noqa: E402

BASE = load_settings()


def empty():
    return {"entries": [], "meta": {"next_id": 1, "telegram_offset": 0}}


class TestParse(unittest.TestCase):
    def test_command_with_bot_suffix(self):
        self.assertEqual(tj.parse_command("/add@sm_bot LONG DOGE +2"), ("/add", ["LONG", "DOGE", "+2"]))

    def test_plain_text_ignored(self):
        self.assertEqual(tj.parse_command("hello"), ("", []))


class TestAdd(unittest.TestCase):
    def test_add_and_counters(self):
        data = empty()
        reply = tj.handle_command("/add", ["long", "dogeusdt", "+2.5%", "TP2"], data)
        self.assertIn("✅", reply)
        self.assertEqual(len(data["entries"]), 1)
        entry = data["entries"][0]
        self.assertEqual(entry["side"], "LONG")
        self.assertEqual(entry["symbol"], "DOGE")
        self.assertAlmostEqual(entry["result_pct"], 2.5)
        self.assertEqual(entry["note"], "TP2")
        self.assertEqual(data["meta"]["next_id"], 2)

    def test_bad_side(self):
        data = empty()
        reply = tj.handle_command("/add", ["SIDEWAYS", "DOGE", "2"], data)
        self.assertIn("LONG ya SHORT", reply)
        self.assertEqual(data["entries"], [])

    def test_bad_number(self):
        data = empty()
        reply = tj.handle_command("/add", ["LONG", "DOGE", "abc"], data)
        self.assertIn("number", reply)
        self.assertEqual(data["entries"], [])


class TestStats(unittest.TestCase):
    def test_stats_math(self):
        data = empty()
        for args in (["LONG", "DOGE", "+2"], ["SHORT", "ADA", "-1"], ["LONG", "XLM", "+3"]):
            tj.handle_command("/add", args, data)
        text = tj.stats_text(data)
        self.assertIn("Trades: 3", text)
        self.assertIn("Win: 2", text)
        self.assertIn("Loss: 1", text)
        self.assertIn("Net: +4.00%", text)
        self.assertIn("Win rate: 66.7%", text)

    def test_list_and_delete(self):
        data = empty()
        tj.handle_command("/add", ["LONG", "DOGE", "+2"], data)
        tj.handle_command("/add", ["SHORT", "ADA", "-1"], data)
        self.assertIn("#2", tj.list_text(data))
        reply = tj.handle_command("/del", ["1"], data)
        self.assertIn("delete", reply)
        self.assertEqual([e["id"] for e in data["entries"]], [2])
        self.assertIn("nahi mila", tj.handle_command("/del", ["9"], data))


class TestPoll(unittest.TestCase):
    def test_only_own_chat_and_offset_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trade.json")
            settings = replace(
                BASE,
                dry_run=False,
                telegram_token="token",
                telegram_chat_id="111",
                trade_journal_path=path,
            )
            updates = [
                {"update_id": 10, "message": {"chat": {"id": 999}, "text": "/add LONG DOGE +5"}},
                {"update_id": 11, "message": {"chat": {"id": 111}, "text": "/add LONG DOGE +2"}},
            ]
            sent = []
            with patch.object(tj, "_fetch_updates", return_value=updates), patch.object(
                tj.notifier, "send_text", side_effect=lambda text, s: sent.append(text) or True
            ):
                handled = tj.poll(settings)

            self.assertEqual(handled, 1)
            data = tj.load(path)
            self.assertEqual(len(data["entries"]), 1)
            self.assertEqual(data["entries"][0]["result_pct"], 2.0)
            self.assertEqual(data["meta"]["telegram_offset"], 12)
            self.assertTrue(any("✅" in m for m in sent))

    def test_dry_run_skips(self):
        settings = replace(BASE, dry_run=True)
        with patch.object(tj, "_fetch_updates", side_effect=AssertionError("no fetch")):
            self.assertEqual(tj.poll(settings), 0)


if __name__ == "__main__":
    unittest.main()
