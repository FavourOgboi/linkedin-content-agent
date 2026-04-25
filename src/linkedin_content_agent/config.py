from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_RSS_FEEDS = (
    "https://hnrss.org/frontpage",
    "https://www.dataengineeringweekly.com/feed",
    "https://www.theseattledataguy.com/feed",
    "https://blog.bytebytego.com/feed",
    "https://realpython.com/atom.xml",
    "https://pycoders.com/feed",
    "https://towardsdatascience.com/feed",
    "https://www.fast.ai/index.xml",
    "https://huggingface.co/blog/feed.xml",
)

DEFAULT_REDDIT_SUBREDDITS = (
    "MachineLearning",
    "datascience",
    "dataengineering",
    "learnpython",
    "Python",
)

DEPRECATED_RSS_FEED_REPLACEMENTS = {
    "https://www.deeplearning.ai/the-batch/feed/": (
        "https://simonwillison.net/atom/everything/",
    ),
}


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_dotenv_file(path: Path | None = None) -> None:
    dotenv_path = path or Path(".env")
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = _strip_quotes(value.strip())


def _split_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _csv_from_env(name: str) -> tuple[str, ...] | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    return _split_csv(raw)


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        ordered.append(value)
        seen.add(value)
    return tuple(ordered)


def _normalize_rss_feeds(feeds: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for feed in feeds:
        replacement = DEPRECATED_RSS_FEED_REPLACEMENTS.get(feed)
        if replacement is not None:
            normalized.extend(replacement)
            continue
        normalized.append(feed)
    return _unique(tuple(normalized))


def _normalize_subreddits(subreddits: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for subreddit in subreddits:
        cleaned = subreddit.strip().removeprefix("r/").removeprefix("/r/")
        if cleaned:
            normalized.append(cleaned)
    return _unique(tuple(normalized))


def _get_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value or default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class SMTPConfig:
    host: str | None
    port: int
    username: str | None
    password: str | None
    use_ssl: bool
    sender: str | None
    recipient: str | None

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.sender and self.recipient)


@dataclass(slots=True)
class AppConfig:
    openai_api_key: str | None
    openai_model: str
    selection_reasoning: str
    generation_reasoning: str
    audit_reasoning: str
    timezone: str
    data_dir: Path
    review_base_url: str | None
    signal_limit_per_source: int
    rss_feeds: tuple[str, ...]
    reddit_subreddits: tuple[str, ...]
    youtube_channel_ids: tuple[str, ...]
    smtp: SMTPConfig
    run_notes_dir: Path

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv_file()
        data_dir = Path(os.getenv("LCA_DATA_DIR", "data"))
        rss_feeds = _csv_from_env("LCA_RSS_FEEDS")
        reddit_subreddits = _csv_from_env("LCA_REDDIT_SUBREDDITS")
        youtube_channel_ids = _csv_from_env("LCA_YOUTUBE_CHANNEL_IDS")
        smtp = SMTPConfig(
            host=os.getenv("LCA_SMTP_HOST"),
            port=int(_get_str("LCA_SMTP_PORT", "465")),
            username=os.getenv("LCA_SMTP_USERNAME"),
            password=os.getenv("LCA_SMTP_PASSWORD"),
            use_ssl=_get_bool("LCA_SMTP_USE_SSL", True),
            sender=os.getenv("LCA_EMAIL_FROM"),
            recipient=os.getenv("LCA_EMAIL_TO"),
        )
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=_get_str("LCA_OPENAI_MODEL", "gpt-5.1"),
            selection_reasoning=_get_str("LCA_OPENAI_SELECTION_REASONING", "low"),
            generation_reasoning=_get_str("LCA_OPENAI_GENERATION_REASONING", "medium"),
            audit_reasoning=_get_str("LCA_OPENAI_AUDIT_REASONING", "low"),
            timezone=_get_str("LCA_TIMEZONE", "Africa/Lagos"),
            data_dir=data_dir,
            review_base_url=os.getenv("LCA_REVIEW_BASE_URL"),
            signal_limit_per_source=int(_get_str("LCA_SIGNAL_LIMIT_PER_SOURCE", "10")),
            rss_feeds=_normalize_rss_feeds(DEFAULT_RSS_FEEDS if rss_feeds is None else rss_feeds),
            reddit_subreddits=_normalize_subreddits(
                DEFAULT_REDDIT_SUBREDDITS if reddit_subreddits is None else reddit_subreddits
            ),
            youtube_channel_ids=() if youtube_channel_ids is None else youtube_channel_ids,
            smtp=smtp,
            run_notes_dir=Path(os.getenv("LCA_RUN_NOTES_DIR", str(data_dir / "run_notes"))),
        )

    @property
    def creator_context(self) -> str:
        return (
            "The creator has a background in data science and analytics and now writes across "
            "AI systems, machine learning, data engineering, Python, backend development, APIs, "
            "SQL, Excel, and practical builder workflows. The voice should feel like a thinking "
            "builder who teaches clearly, shares perspective, and values honest insight over hype."
        )
