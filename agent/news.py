"""Crypto + forex + macro news digest (Hinglish / Roman Urdu).

Public RSS feeds se headlines aate hain, duplicate hata kar, rule-based
Hinglish summary banti hai. Ye AI translation nahi hai — isliye original
English headline bhi saath diya jata hai taake misreading na ho.

Digest har NEWS_INTERVAL_HOURS par ek dafa jata hai (journal meta mein
last_news_at save hota hai).
"""

from __future__ import annotations

import email.utils
import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from . import notifier
from .config import Settings

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; crypto-signal-agent/1.0)"
TIMEOUT = 15
MAX_SEEN = 600


@dataclass(frozen=True)
class Feed:
    category: str
    source: str
    url: str


FEEDS = (
    Feed("Crypto", "Cointelegraph", "https://cointelegraph.com/rss"),
    Feed("Crypto", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    Feed("Crypto", "Decrypt", "https://decrypt.co/feed"),
    Feed("Forex", "ForexLive", "https://www.forexlive.com/feed/news"),
    Feed("Markets", "CNBC Markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
)

CATEGORY_HEADERS = (
    ("Crypto", "🪙 CRYPTO"),
    ("Forex", "💱 FOREX"),
    ("Markets", "📈 MARKETS / MACRO"),
)

_TOPICS = (
    (r"\bbitcoin\b|\bbtc\b", "Bitcoin"),
    (r"\bethereum\b|\beth\b", "Ethereum"),
    (r"\bsolana\b|\bsol\b", "Solana"),
    (r"\bripple\b|\bxrp\b", "XRP"),
    (r"\bdogecoin\b|\bdoge\b", "Dogecoin"),
    (r"\bshiba\b|\bshib\b", "SHIB"),
    (r"\bcardano\b|\bada\b", "Cardano"),
    (r"\bhedera\b|\bhbar\b", "Hedera"),
    (r"\bbinance\b|\bbnb\b", "Binance"),
    (r"\bcoinbase\b", "Coinbase"),
    (r"\bfederal reserve\b|\bfed\b|\bfomc\b|\bpowell\b", "Federal Reserve"),
    (r"\bdollar\b|\bdxy\b|\busd\b", "Dollar"),
    (r"\beuro\b|\becb\b", "Euro"),
    (r"\byen\b|\bboj\b", "Yen"),
    (r"\bpound\b|\bgbp\b|\bboe\b", "Pound"),
    (r"\bgold\b|\bxau\b|\bbullion\b", "Gold"),
    (r"\bcrude\b|\bbrent\b|\boil\b", "Oil"),
    (r"\bs&p\b|\bsp500\b", "S&P 500"),
    (r"\bnasdaq\b", "Nasdaq"),
    (r"\bdow jones\b|\bdow\b", "Dow Jones"),
)

_BULL = re.compile(
    r"\b(surge\w*|soar\w*|rally|rallies|rallied|jump\w*|climb\w*|gain\w*|rise|rises|rising|"
    r"record high|all-time high|ath|bullish|rebound\w*|recover\w*|breakout|approval|approves)\b"
)
_BEAR = re.compile(
    r"\b(plunge\w*|slump\w*|crash\w*|tumble\w*|sink\w*|slide\w*|drop\w*|fall|falls|falling|"
    r"decline\w*|bearish|sell-?off|liquidat\w*|record low|dump\w*|hack\w*|exploit\w*|ban\w*|prob\w*)\b"
)

# Crypto feeds mein AI/tech gossip bhi aata hai — sirf relevant headlines rakhte hain.
_CRYPTO_HINT = re.compile(
    r"\b(bitcoin|btc|ethereum|eth|crypto\w*|blockchain|token\w*|defi|stablecoin\w*|"
    r"altcoin\w*|web3|nft\w*|mining|miner\w*|wallet\w*|exchange|binance|coinbase|"
    r"solana|xrp|ripple|dogecoin|shiba|cardano|hedera|polkadot|chainlink|etf|sec|"
    r"custody|on-?chain|whale\w*|coin)\b"
)

_EVENTS = (
    (r"\betf\b", "ETF"),
    (r"\b(approv\w*|approval)\b", "approve hua"),
    (r"\binflow\w*", "paisa andar aaya"),
    (r"\boutflow\w*", "paisa bahar gaya"),
    (r"\b(rate cut|cuts? rates?|rate cuts?|dovish)\b", "interest rate kam"),
    (r"\b(rate hike|hikes? rates?|rate hikes?|hawkish)\b", "interest rate barha"),
    (r"\binflation\b", "mehangai"),
    (r"\bcpi\b", "CPI data"),
    (r"\b(nonfarm|payrolls|jobs report)\b", "US jobs data"),
    (r"\b(hack\w*|exploit\w*|breach\w*)\b", "hack/exploit"),
    (r"\bban\w*\b", "ban"),
    (r"\b(lawsuit|sue\w*|court|charges?)\b", "legal case"),
    (r"\b(fine\w*|penalt\w*|settle\w*)\b", "penalty/settlement"),
    (r"\bhalving\b", "halving"),
    (r"\b(delist\w*|listing)\b", "listing/delisting"),
    (r"\b(upgrade|fork)\b", "network upgrade"),
    (r"\bregulat\w*", "regulation"),
    (r"\bwhale\w*", "bade wallets active"),
    (r"\bliquidat\w*", "liquidation"),
    (r"\b(partnership|partner\w*|deal)\b", "partnership/deal"),
    (r"\b(launch\w*|unveil\w*)\b", "launch"),
    (r"\b(record high|all-time high)\b", "record high"),
    (r"\b(war|attack\w*|strike\w*|conflict|sanction\w*)\b", "geopolitical tension"),
    (r"\b(recession)\b", "recession ka dar"),
    (r"\b(tariff\w*)\b", "tariff news"),
    (r"\b(layoff\w*|cuts? jobs?|job cuts?|slash\w* staff)\b", "staff cut/layoffs"),
    (r"\bcapitulat\w*", "panic selling"),
    (r"\b(tokeni[sz]\w*|government bonds?|treasur\w*)\b", "tokenized bonds/govt paper"),
    (r"\b(acqui\w*|merger|m&a)\b", "merger/acquisition"),
    (r"\b(ipo|funding round|raise[sd]? \$)\b", "funding news"),
    (r"\bbull run\b", "bull run"),
    (r"\b(multi-?year low|3-month low|four-month low)\b", "multi-month low"),
)


@dataclass
class NewsItem:
    title: str
    link: str
    published_ms: int
    source: str
    category: str

    @property
    def uid(self) -> str:
        norm = re.sub(r"[^a-z0-9]+", "", self.title.lower())[:80]
        return hashlib.md5(norm.encode()).hexdigest()[:12]


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node, *names: str) -> str:
    wanted = set(names)
    for child in node:
        if _local(child.tag) in wanted:
            if child.text and child.text.strip():
                return _clean(child.text)
    return ""


def _child_link(node) -> str:
    for child in node:
        if _local(child.tag) != "link":
            continue
        href = child.attrib.get("href", "").strip()
        if child.text and child.text.strip():
            return child.text.strip()
        if href:
            return href
    return ""


def _parse_date(raw: str) -> int:
    if not raw:
        return 0
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return 0


def parse_feed(xml_text: str, source: str, category: str) -> list[NewsItem]:
    """RSS 2.0 aur Atom dono parse karta hai (namespace-agnostic)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items: list[NewsItem] = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title = _child_text(node, "title")
        link = _child_link(node) or _child_text(node, "guid", "id")
        published = _child_text(node, "pubdate", "published", "updated", "date")
        if not title or not link:
            continue
        items.append(
            NewsItem(
                title=title,
                link=link,
                published_ms=_parse_date(published),
                source=source,
                category=category,
            )
        )
    return items


def fetch_feed(feed: Feed) -> list[NewsItem]:
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = requests.get(feed.url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            resp.raise_for_status()
            return parse_feed(resp.text, feed.source, feed.category)
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(1.5)
    assert last_exc is not None
    raise last_exc


def collect(settings: Settings, now_ms: int) -> list[NewsItem]:
    cutoff = now_ms - int(settings.news_lookback_hours * 3_600_000)
    items: list[NewsItem] = []
    for feed in FEEDS:
        try:
            items.extend(fetch_feed(feed))
        except (requests.RequestException, ValueError) as exc:
            log.warning("News feed %s fail: %s", feed.source, exc)

    seen: set[str] = set()
    fresh: list[NewsItem] = []
    for item in sorted(items, key=lambda x: x.published_ms, reverse=True):
        if item.published_ms and item.published_ms < cutoff:
            continue
        if item.category == "Crypto" and not _CRYPTO_HINT.search(item.title.lower()):
            continue
        if item.uid in seen:
            continue
        seen.add(item.uid)
        fresh.append(item)
    return fresh


def select_items(items: list[NewsItem], settings: Settings, seen_ids: set[str]) -> list[NewsItem]:
    caps = {
        "Crypto": settings.news_max_crypto,
        "Forex": settings.news_max_macro,
        "Markets": settings.news_max_macro,
    }
    picked: list[NewsItem] = []
    counts: dict[str, int] = {}
    for item in items:
        if item.uid in seen_ids:
            continue
        cap = caps.get(item.category, 0)
        if counts.get(item.category, 0) >= cap:
            continue
        counts[item.category] = counts.get(item.category, 0) + 1
        picked.append(item)
    return picked


def hinglish_line(title: str) -> str:
    text = title.lower()

    topic = ""
    best_pos = None
    for pattern, label in _TOPICS:
        match = re.search(pattern, text)
        if match and (best_pos is None or match.start() < best_pos):
            topic, best_pos = label, match.start()

    events: list[str] = []
    for pattern, label in _EVENTS:
        if label in events:
            continue
        if re.search(pattern, text):
            events.append(label)

    bias = ""
    if _BULL.search(text) and not _BEAR.search(text):
        bias = " — bullish 🟢"
    elif _BEAR.search(text) and not _BULL.search(text):
        bias = " — bearish 🔴"

    body = ", ".join(events[:3]) if events else "market update"
    return f"{topic or 'Market'}: {body}{bias}"


def build_digest(picked: list[NewsItem], now_ms: int) -> str:
    stamp = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    lines = [f"📰 Market News — Hinglish Digest", f"🕒 {stamp}"]

    for category, header in CATEGORY_HEADERS:
        group = [it for it in picked if it.category == category]
        if not group:
            continue
        lines.append("")
        lines.append(header)
        for item in group:
            lines.append(f"• {hinglish_line(item.title)}")
            lines.append(f"  EN: {item.title}")
            lines.append(f"  {item.source} — {item.link}")

    lines.append("")
    lines.append("ℹ️ Hinglish line rule-based hai (AI translation nahi). Original headline aur link saath diye hain.")
    return "\n".join(lines)


def _last_sent_ms(meta: dict) -> int:
    raw = meta.get("last_news_at")
    if not raw:
        return 0
    try:
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return 0


def maybe_send(settings: Settings, jrnl: dict, now_ms: int) -> bool:
    if not settings.news_enabled:
        return False

    meta = jrnl.setdefault("meta", {})
    last = _last_sent_ms(meta)
    if last and now_ms - last < int(settings.news_interval_hours * 3_600_000):
        return False

    seen = set(meta.get("news_seen") or [])
    picked = select_items(collect(settings, now_ms), settings, seen)
    if not picked:
        log.info("News: koi naya item nahi mila")
        return False

    if not notifier.send_text(build_digest(picked, now_ms), settings):
        log.error("News digest send fail")
        return False

    history = (meta.get("news_seen") or []) + [it.uid for it in picked]
    meta["news_seen"] = history[-MAX_SEEN:]
    meta["last_news_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return True
