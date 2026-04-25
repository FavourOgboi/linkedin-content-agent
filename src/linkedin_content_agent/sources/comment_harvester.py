from __future__ import annotations

from abc import ABC, abstractmethod
import json
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

from linkedin_content_agent.models import CommentInsight, CommentSignalStrength, CommentSentiment, SourceReference, TopicContext
from linkedin_content_agent.sources.base import Loader, fetch_bytes


HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

SKEPTICAL_MARKERS = (
    "but",
    "however",
    "actually",
    "wrong",
    "issue",
    "problem",
    "break",
    "breaks",
    "failed",
    "fails",
    "doesn't work",
    "does not work",
    "overkill",
    "brittle",
    "limited",
)
EXCITED_MARKERS = (
    "great",
    "love",
    "useful",
    "nice",
    "finally",
    "impressive",
    "solid",
    "helpful",
)
PRACTICAL_MARKERS = (
    "in production",
    "in practice",
    "at scale",
    "workflow",
    "latency",
    "cost",
    "schema",
    "pipeline",
    "debug",
    "deployment",
)
QUESTION_MARKERS = ("why", "how", "when", "what", "does", "do", "should", "can", "is", "are")


def _clean_comment_text(text: str) -> str:
    normalized = HTML_TAG_RE.sub(" ", text or "")
    normalized = normalized.replace("&quot;", '"').replace("&#x27;", "'").replace("&amp;", "&")
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def _first_sentence(text: str) -> str:
    cleaned = _clean_comment_text(text)
    if not cleaned:
        return ""
    return SENTENCE_SPLIT_RE.split(cleaned, maxsplit=1)[0].strip()


def _shorten(text: str, *, limit: int = 140) -> str:
    cleaned = _clean_comment_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _classify_sentiment(comments: list[str]) -> CommentSentiment:
    if not comments:
        return "unknown"
    haystack = " ".join(comment.lower() for comment in comments)
    skeptical = sum(marker in haystack for marker in SKEPTICAL_MARKERS)
    excited = sum(marker in haystack for marker in EXCITED_MARKERS)
    practical = sum(marker in haystack for marker in PRACTICAL_MARKERS)
    if practical >= max(skeptical, excited, 1):
        return "practical"
    if skeptical > excited * 1.4:
        return "skeptical"
    if excited > skeptical * 1.4:
        return "excited"
    return "divided"


def _signal_strength(comment_count: int) -> CommentSignalStrength:
    if comment_count >= 10:
        return "high"
    if comment_count >= 4:
        return "medium"
    return "low"


def _paraphrase_comment(comment: str) -> str:
    sentence = _first_sentence(comment)
    if not sentence:
        return ""
    lowered = sentence.lower()
    stem = _shorten(sentence, limit=110)
    if any(marker in lowered for marker in SKEPTICAL_MARKERS):
        return f"Skeptics argue that {stem}"
    if any(marker in lowered for marker in EXCITED_MARKERS):
        return f"Supporters think {stem}"
    if any(marker in lowered for marker in PRACTICAL_MARKERS):
        return f"A practical point raised is {stem}"
    return f"One recurring reaction is {stem}"


def _strongest_pushback(comments: list[str]) -> str:
    for comment in comments:
        lowered = comment.lower()
        if any(marker in lowered for marker in SKEPTICAL_MARKERS):
            return f"The strongest pushback is that {_shorten(comment)}"
    return ""


def _common_question(comments: list[str]) -> str:
    for comment in comments:
        sentence = _first_sentence(comment)
        lowered = sentence.lower()
        if "?" in sentence or any(lowered.startswith(marker) for marker in QUESTION_MARKERS):
            return f"The recurring question is {_shorten(sentence)}"
    return ""


def summarize_comments(*, source: str, comments: list[str]) -> CommentInsight | None:
    cleaned_comments = [_clean_comment_text(comment) for comment in comments if _clean_comment_text(comment)]
    if not cleaned_comments:
        return None

    debates: list[str] = []
    seen: set[str] = set()
    for comment in cleaned_comments:
        paraphrase = _paraphrase_comment(comment)
        if not paraphrase:
            continue
        key = paraphrase.lower()
        if key in seen:
            continue
        debates.append(paraphrase)
        seen.add(key)
        if len(debates) >= 5:
            break

    return CommentInsight(
        source=source,
        comment_count=len(cleaned_comments),
        top_sentiment=_classify_sentiment(cleaned_comments),
        signal_strength=_signal_strength(len(cleaned_comments)),
        key_debates=debates,
        strongest_pushback=_strongest_pushback(cleaned_comments),
        common_question=_common_question(cleaned_comments),
    )


class BaseCommentSource(ABC):
    @abstractmethod
    def can_handle(self, topic_context: TopicContext) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, topic_context: TopicContext) -> CommentInsight | None:
        raise NotImplementedError


class HNCommentSource(BaseCommentSource):
    def __init__(self, loader: Loader = fetch_bytes, *, max_comments: int = 15) -> None:
        self.loader = loader
        self.max_comments = max_comments

    def can_handle(self, topic_context: TopicContext) -> bool:
        return topic_context.dossier.primary_signal.source.lower() == "hackernews"

    def fetch(self, topic_context: TopicContext) -> CommentInsight | None:
        reference = topic_context.dossier.primary_signal
        story_id = self._extract_story_id(reference) or self._lookup_story_id(reference)
        if not story_id:
            return None

        story = self._load_json(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
        comment_ids = (story.get("kids") or [])[: self.max_comments]
        comments: list[str] = []
        for comment_id in comment_ids:
            item = self._load_json(f"https://hacker-news.firebaseio.com/v0/item/{comment_id}.json")
            if item.get("dead") or item.get("deleted"):
                continue
            text = _clean_comment_text(str(item.get("text", "")))
            if text:
                comments.append(text)
        return summarize_comments(source="hackernews", comments=comments)

    def _extract_story_id(self, reference: SourceReference) -> str | None:
        parsed = urlparse(reference.url)
        if parsed.netloc.endswith("ycombinator.com") and parsed.path.endswith("/item"):
            return parse_qs(parsed.query).get("id", [None])[0]
        return None

    def _lookup_story_id(self, reference: SourceReference) -> str | None:
        query = quote_plus(reference.title)
        payload = self._load_json(f"https://hn.algolia.com/api/v1/search?tags=story&query={query}")
        hits = payload.get("hits", [])
        if not hits:
            return None

        target_url = reference.url.rstrip("/")
        for hit in hits:
            if str(hit.get("url", "")).rstrip("/") == target_url:
                object_id = hit.get("objectID")
                return str(object_id) if object_id else None

        first = hits[0]
        object_id = first.get("objectID")
        return str(object_id) if object_id else None

    def _load_json(self, url: str) -> dict[str, Any]:
        return json.loads(self.loader(url).decode("utf-8"))


class RedditCommentSource(BaseCommentSource):
    def __init__(self, loader: Loader = fetch_bytes, *, max_comments: int = 10) -> None:
        self.loader = loader
        self.max_comments = max_comments

    def can_handle(self, topic_context: TopicContext) -> bool:
        return topic_context.dossier.primary_signal.source.lower().startswith("reddit:")

    def fetch(self, topic_context: TopicContext) -> CommentInsight | None:
        reference = topic_context.dossier.primary_signal
        parsed = urlparse(reference.url)
        path = parsed.path.strip("/").split("/")
        if "comments" not in path:
            return None

        subreddit = path[1] if len(path) > 1 else ""
        post_id_index = path.index("comments") + 1
        if post_id_index >= len(path):
            return None
        post_id = path[post_id_index]
        url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?limit={self.max_comments}"
        payload = json.loads(self.loader(url).decode("utf-8"))
        if len(payload) < 2:
            return None

        children = payload[1].get("data", {}).get("children", [])
        scored_comments: list[tuple[int, str]] = []
        for item in children:
            data = item.get("data", {})
            body = _clean_comment_text(str(data.get("body", "")))
            score = int(data.get("score", 0) or 0)
            if not body or body == "[deleted]" or score < 5:
                continue
            scored_comments.append((score, body))

        scored_comments.sort(key=lambda item: item[0], reverse=True)
        comments = [comment for _, comment in scored_comments[: self.max_comments]]
        return summarize_comments(source=f"reddit:{subreddit}", comments=comments)


class CommentHarvester:
    def __init__(self, sources: list[BaseCommentSource] | None = None) -> None:
        self.sources = sources or [HNCommentSource(), RedditCommentSource()]

    def harvest(self, topic_context: TopicContext) -> CommentInsight | None:
        for source in self.sources:
            if not source.can_handle(topic_context):
                continue
            try:
                return source.fetch(topic_context)
            except Exception:
                return None
        return None
