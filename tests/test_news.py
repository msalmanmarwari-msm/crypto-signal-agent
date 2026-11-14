import os
import sys
import time
import unittest
from dataclasses import replace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import news  # noqa: E402
from agent.config import load_settings  # noqa: E402

BASE = load_settings()

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title><![CDATA[Bitcoin ETF sees record inflows as price surges]]></title>
    <link>https://example.com/a?utm_source=rss</link>
    <pubDate>Sat, 15 Nov 2026 10:00:00 +0000</pubDate>
  </item>
  <item>
    <title>Ethereum plunges after exchange hack, lawsuit filed</title>
    <link>https://example.com/b</link>
    <pubDate>Sat, 15 Nov 2026 09:00:00 GMT</pubDate>
  </item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Gold climbs as Fed signals rate cut</title>
    <link rel="alternate" href="https://example.com/c"/>
    <updated>2026-11-15T08:00:00Z</updated>
  </entry>
</feed>"""


class TestParse(unittest.TestCase):
    def test_rss_items(self):
        items = news.parse_feed(RSS, "TestFeed", "Crypto")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "Bitcoin ETF sees record inflows as price surges")
        self.assertEqual(items[0].link, "https://example.com/a?utm_source=rss")
        self.assertGreater(items[0].published_ms, 0)

    def test_atom_entry(self):
        items = news.parse_feed(ATOM, "AtomFeed", "Markets")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].link, "https://example.com/c")
        self.assertGreater(items[0].published_ms, 0)

    def test_broken_xml_returns_empty(self):
        self.assertEqual(news.parse_feed("<rss><channel>", "x", "Crypto"), [])


class TestHinglish(unittest.TestCase):
    def test_bullish_crypto(self):
        line = news.hinglish_line("Bitcoin ETF sees record inflows as price surges")
        self.assertIn("Bitcoin", line)
        self.assertIn("ETF", line)
        self.assertIn("bullish", line)

    def test_bearish_risk_news(self):
        line = news.hinglish_line("Ethereum plunges after exchange hack, lawsuit filed")
        self.assertIn("Ethereum", line)
        self.assertIn("hack", line)
        self.assertIn("bearish", line)

    def test_macro_rate_cut(self):
        line = news.hinglish_line("Gold climbs as Fed signals rate cut")
        self.assertIn("Gold", line)
        self.assertIn("interest rate kam", line)
        self.assertIn("bullish", line)

    def test_unknown_title_falls_back(self):
        self.assertIn("market update", news.hinglish_line("Something entirely unexpected"))


class TestSelect(unittest.TestCase):
    def _item(self, title, category):
        return news.NewsItem(title, f"https://example.com/{abs(hash(title))}", 1, "src", category)

    def test_category_caps_and_seen(self):
        settings = replace(BASE, news_max_crypto=1, news_max_macro=1)
        items = [
            self._item("Bitcoin one", "Crypto"),
            self._item("Bitcoin two", "Crypto"),
            self._item("Fed one", "Markets"),
            self._item("Fed two", "Markets"),
        ]
        picked = news.select_items(items, settings, set())
        self.assertEqual([i.title for i in picked], ["Bitcoin one", "Fed one"])

        seen = {picked[0].uid}
        picked2 = news.select_items(items, settings, seen)
        self.assertEqual([i.title for i in picked2], ["Bitcoin two", "Fed one"])

    def test_digest_has_sections_and_link(self):
        picked = [
            self._item("Bitcoin ETF sees record inflows", "Crypto"),
            self._item("Gold climbs as Fed signals rate cut", "Markets"),
        ]
        text = news.build_digest(picked, int(time.time() * 1000))
        self.assertIn("CRYPTO", text)
        self.assertIn("MARKETS", text)
        self.assertNotIn("FOREX", text)
        self.assertIn("EN: Bitcoin ETF sees record inflows", text)
        self.assertIn("https://example.com/", text)


class TestMaybeSend(unittest.TestCase):
    def test_interval_gate(self):
        settings = replace(BASE, news_enabled=True, news_interval_hours=6)
        jrnl = {"signals": [], "meta": {}}
        now_ms = int(time.time() * 1000)
        item = news.NewsItem("Bitcoin surges to record high", "https://example.com/x", now_ms, "src", "Crypto")

        with patch.object(news, "collect", return_value=[item]), patch.object(
            news.notifier, "send_text", return_value=True
        ):
            self.assertTrue(news.maybe_send(settings, jrnl, now_ms))
            self.assertFalse(news.maybe_send(settings, jrnl, now_ms))

        self.assertIn("last_news_at", jrnl["meta"])
        self.assertEqual(len(jrnl["meta"]["news_seen"]), 1)

    def test_disabled_does_nothing(self):
        settings = replace(BASE, news_enabled=False)
        jrnl = {"signals": [], "meta": {}}
        with patch.object(news, "collect", side_effect=AssertionError("should not fetch")):
            self.assertFalse(news.maybe_send(settings, jrnl, int(time.time() * 1000)))


if __name__ == "__main__":
    unittest.main()
