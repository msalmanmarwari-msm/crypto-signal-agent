import os
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import live, strategy, trade_journal as tj  # noqa: E402
from agent.config import WARMUP_1H, load_settings  # noqa: E402

BASE = load_settings()


def empty():
    return {"entries": [], "meta": {"next_id": 1, "telegram_offset": 0}}


class TestResolve(unittest.TestCase):
    def test_short_name_and_full_symbol(self):
        self.assertEqual(live.resolve_symbol(BASE, "xlm"), "XLMUSDT")
        self.assertEqual(live.resolve_symbol(BASE, "XLMUSDT"), "XLMUSDT")
        self.assertEqual(live.resolve_symbol(BASE, " xlm/usdt "), "XLMUSDT")

    def test_unknown_coin(self):
        self.assertIsNone(live.resolve_symbol(BASE, "BTC"))
        self.assertIsNone(live.resolve_symbol(BASE, ""))


class TestSignalsText(unittest.TestCase):
    def test_empty(self):
        self.assertIn("koi signal nahi", live.signals_text({"signals": [], "meta": {}}))

    def test_open_and_closed(self):
        jrnl = {
            "signals": [
                {"symbol": "XLMUSDT", "side": "SHORT", "status": "OPEN", "entry": 0.13, "tp1": 0.128},
                {"symbol": "ADAUSDT", "side": "SHORT", "status": "WIN", "outcome_r": 1.5},
                {"symbol": "VETUSDT", "side": "SHORT", "status": "LOSS", "outcome_r": -1.0},
            ],
            "meta": {},
        }
        text = live.signals_text(jrnl)
        self.assertIn("SHORT XLM", text)
        self.assertIn("WIN", text)
        self.assertIn("Win rate: 50.0%", text)


class TestStatusText(unittest.TestCase):
    def test_status_contains_run_and_personal(self):
        jrnl = {"signals": [], "meta": {"last_run": "2026-11-14T22:52:23Z", "last_news_at": "2026-11-14T21:03:07Z"}}
        tdata = {"entries": [{"id": 1, "result_pct": 2.5}, {"id": 2, "result_pct": -1.0}], "meta": {}}
        text = live.status_text(BASE, jrnl, tdata)
        self.assertIn("AGENT STATUS", text)
        self.assertIn("2026-11-14T22:52:23Z", text)
        self.assertIn("2 trades, net +1.50%", text)


class TestHandle(unittest.TestCase):
    def test_missing_arg(self):
        self.assertIn("Format", live.handle("/setup", [], BASE, {"signals": [], "meta": {}}, empty()))

    def test_unknown_coin_lists_symbols(self):
        reply = live.handle("/price", ["BTC"], BASE, {"signals": [], "meta": {}}, empty())
        self.assertIn("list mein nahi", reply)
        self.assertIn("XLM", reply)

    def test_data_failure_is_friendly(self):
        with patch.object(live, "fetch_prepared", side_effect=RuntimeError("boom")):
            reply = live.handle("/price", ["XLM"], BASE, {"signals": [], "meta": {}}, empty())
        self.assertIn("Data fetch fail", reply)

    def test_journal_router_reaches_live_commands(self):
        reply = tj.handle_command("/status", [], empty(), BASE, {"signals": [], "meta": {}})
        self.assertIn("AGENT STATUS", reply)

    def test_journal_router_without_settings_is_old_behaviour(self):
        self.assertIn("samajh nahi aayi", tj.handle_command("/status", [], empty()))


class TestPlainQuery(unittest.TestCase):
    def test_plain_symbol_answers(self):
        with patch.object(live, "setup_text", return_value="XLM analysis"):
            self.assertEqual(live.plain_query(BASE, "xlm?"), "XLM analysis")

    def test_other_text_ignored(self):
        self.assertIsNone(live.plain_query(BASE, "thanks bro"))
        self.assertIsNone(live.plain_query(BASE, "BTC"))


class TestServe(unittest.TestCase):
    def test_worker_polls_and_commits_batches(self):
        handled = iter([1, 0])
        batches = []
        clock = iter([0.0, 0.0, 5.0, 100.0])
        with patch.object(tj, "poll", side_effect=lambda *a, **k: next(handled)), patch.object(
            tj.time, "monotonic", side_effect=lambda: next(clock, 100.0)
        ):
            total = tj.serve(BASE, minutes=0.1, on_batch=lambda: batches.append(1))
        self.assertEqual(total, 1)
        self.assertEqual(len(batches), 1)

    def test_poll_can_be_disabled_for_scan_job(self):
        with patch.dict(os.environ, {"TELEGRAM_POLL": "0"}):
            self.assertFalse(load_settings().telegram_poll)
        with patch.dict(os.environ, {"TELEGRAM_POLL": "1"}):
            self.assertTrue(load_settings().telegram_poll)


def _frame(rows, **cols):
    data = {"close_time": np.arange(rows, dtype=float) * 900_000}
    for name, value in cols.items():
        data[name] = np.full(rows, float(value))
    return pd.DataFrame(data)


class TestAnalyzeSymbol(unittest.TestCase):
    def test_short_setup_explains_block(self):
        n15 = 60
        df15 = _frame(n15, open=100.0, high=101.2, low=98.8, close=100.0, atr=1.0, ema20=100.5)
        df15.loc[n15 - 1, ["open", "high", "low", "close"]] = [101.0, 101.1, 99.0, 99.2]
        df15.loc[n15 - 1, "rsi"] = 45.0
        df15.loc[n15 - 1, "vol_ratio"] = 1.5
        df15["macd_hist"] = np.where(np.arange(n15) == n15 - 1, -0.5, -0.1)
        df15.loc[n15 - 2, "macd_hist"] = -0.1
        df15["swing_low20"] = 95.0
        df15["swing_high20"] = 105.0

        n1h = WARMUP_1H + 20
        last_1h = WARMUP_1H + 10
        # close_time last row ko warmup ke baad wale 1h candle par rakhein
        df15.loc[n15 - 1, "close_time"] = last_1h * 3_600_000

        df1h = _frame(n1h, open=90.0, high=101.0, low=89.0, close=90.0, ema50=95.0, ema200=100.0, rsi=40.0)
        df1h["h4_trend"] = -1.0
        df1h["close_time"] = np.arange(n1h, dtype=float) * 3_600_000
        df1h.loc[last_1h - 10, "ema50"] = 96.0

        a = strategy.analyze_symbol("XLMUSDT", df1h, df15, None, BASE, full=True)
        self.assertIsNotNone(a)
        self.assertEqual(a.side, "SHORT")
        self.assertGreaterEqual(a.short_score, 8)
        self.assertIsNotNone(a.block)
        labels = [label for label, _ in a.gates]
        self.assertIn(f"core score >= {BASE.min_score}", labels)
        self.assertTrue(strategy.evaluate("XLMUSDT", df1h, df15, None, BASE) is None)


if __name__ == "__main__":
    unittest.main()
