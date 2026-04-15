from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import html
import json
from pathlib import Path
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from linkedin_content_agent.models import Signal
from linkedin_content_agent.utils import parse_iso_datetime


USER_AGENT = "linkedin-content-agent/0.1"
Loader = Callable[[str], bytes]
ATOM_NS = "{http://www.w3.org/2005/Atom}"


def fetch_bytes(url: str, *, timeout: int = 20) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def load_fixture_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None

    parsed = parse_iso_datetime(value)
    if parsed:
        return parsed.isoformat()

    try:
        parsed_rfc = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None

    if parsed_rfc.tzinfo is None:
        return parsed_rfc.replace(tzinfo=UTC).isoformat()
    return parsed_rfc.astimezone(UTC).isoformat()


def _text(element: ElementTree.Element | None, default: str = "") -> str:
    if element is None:
        return default
    return "".join(element.itertext()).strip()


def _clean_text(value: str) -> str:
    normalized = html.unescape(value)
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def parse_feed_bytes(payload: bytes, *, source_name: str) -> list[Signal]:
    root = ElementTree.fromstring(payload)
    signals: list[Signal] = []

    if root.tag.endswith("rss"):
        channel = root.find("channel")
        if channel is None:
            return []
        for item in channel.findall("item"):
            title = _text(item.find("title"))
            link = _text(item.find("link"))
            excerpt = _clean_text(_text(item.find("description")))
            if not title or not link:
                continue
            published = _normalize_date(_text(item.find("pubDate")) or _text(item.find("published")))
            signals.append(
                Signal(
                    source=source_name,
                    title=title,
                    url=link,
                    published_at=published,
                    engagement_hint={},
                    excerpt=excerpt,
                    raw_metadata={"guid": _text(item.find("guid"))},
                )
            )
        return signals

    if root.tag == f"{ATOM_NS}feed":
        for entry in root.findall(f"{ATOM_NS}entry"):
            title = _text(entry.find(f"{ATOM_NS}title"))
            summary = _clean_text(_text(entry.find(f"{ATOM_NS}summary")) or _text(entry.find(f"{ATOM_NS}content")))
            link = ""
            for link_node in entry.findall(f"{ATOM_NS}link"):
                href = link_node.attrib.get("href", "")
                rel = link_node.attrib.get("rel", "alternate")
                if href and rel == "alternate":
                    link = href
                    break
                if href and not link:
                    link = href
            if not title or not link:
                continue
            published = _normalize_date(
                _text(entry.find(f"{ATOM_NS}published")) or _text(entry.find(f"{ATOM_NS}updated"))
            )
            signals.append(
                Signal(
                    source=source_name,
                    title=title,
                    url=link,
                    published_at=published,
                    engagement_hint={},
                    excerpt=summary,
                    raw_metadata={"id": _text(entry.find(f"{ATOM_NS}id"))},
                )
            )
        return signals

    return []


def parse_reddit_json(payload: bytes, *, subreddit: str) -> list[Signal]:
    document = json.loads(payload.decode("utf-8"))
    items = document.get("data", {}).get("children", [])
    signals: list[Signal] = []

    for item in items:
        data = item.get("data", {})
        title = (data.get("title") or "").strip()
        permalink = (data.get("permalink") or "").strip()
        if not title or not permalink:
            continue
        excerpt = (data.get("selftext") or data.get("public_description") or "").strip()
        created_utc = data.get("created_utc")
        published = None
        if isinstance(created_utc, (int, float)):
            published = datetime.fromtimestamp(created_utc, UTC).isoformat()
        signals.append(
            Signal(
                source=f"reddit:{subreddit}",
                title=title,
                url=f"https://www.reddit.com{permalink}",
                published_at=published,
                engagement_hint={
                    "score": data.get("score", 0),
                    "num_comments": data.get("num_comments", 0),
                    "upvote_ratio": data.get("upvote_ratio"),
                },
                excerpt=excerpt,
                raw_metadata={
                    "id": data.get("id"),
                    "subreddit": data.get("subreddit"),
                    "author": data.get("author"),
                },
            )
        )
    return signals


class SignalSource(ABC):
    """Base class for compliant signal adapters."""

    @abstractmethod
    def fetch(self) -> list[Signal]:
        raise NotImplementedError


class OfficialApiSourceAdapter(SignalSource, ABC):
    """Reserved interface for future official or paid API-backed social sources."""


class RSSSource(SignalSource):
    def __init__(self, name: str, url: str, *, limit: int = 10, loader: Loader = fetch_bytes) -> None:
        self.name = name
        self.url = url
        self.limit = limit
        self.loader = loader

    def fetch(self) -> list[Signal]:
        payload = self.loader(self.url)
        return parse_feed_bytes(payload, source_name=self.name)[: self.limit]


class RedditHotSource(SignalSource):
    def __init__(self, subreddit: str, *, limit: int = 10, loader: Loader = fetch_bytes) -> None:
        self.subreddit = subreddit
        self.limit = limit
        self.loader = loader

    @property
    def url(self) -> str:
        return f"https://www.reddit.com/r/{self.subreddit}/hot.json?limit={self.limit}"

    @property
    def rss_url(self) -> str:
        return f"https://www.reddit.com/r/{self.subreddit}/.rss"

    def fetch(self) -> list[Signal]:
        try:
            payload = self.loader(self.url)
            return parse_reddit_json(payload, subreddit=self.subreddit)[: self.limit]
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            fallback_payload = self.loader(self.rss_url)
            signals = parse_feed_bytes(fallback_payload, source_name=f"reddit:{self.subreddit}")[: self.limit]
            if not signals:
                raise ValueError(f"No public Reddit signals found for subreddit '{self.subreddit}'.")
            return signals


class YouTubeChannelFeedSource(SignalSource):
    def __init__(self, channel_id: str, *, limit: int = 10, loader: Loader = fetch_bytes) -> None:
        self.channel_id = channel_id
        self.limit = limit
        self.loader = loader

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={self.channel_id}"

    def fetch(self) -> list[Signal]:
        payload = self.loader(self.url)
        signals = parse_feed_bytes(payload, source_name=f"youtube:{self.channel_id}")[: self.limit]
        if not signals:
            raise ValueError(f"No public YouTube uploads found for channel '{self.channel_id}'.")
        return signals


def safe_fetch(source: SignalSource) -> tuple[list[Signal], str | None]:
    try:
        return source.fetch(), None
    except (HTTPError, URLError, TimeoutError, ElementTree.ParseError, json.JSONDecodeError, ValueError) as exc:
        return [], f"{source.__class__.__name__} failed: {exc}"
