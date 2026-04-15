from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_RSS_FEEDS = (
    "https://hnrss.org/frontpage",
    "https://www.deeplearning.ai/the-batch/feed/",
    "https://www.kdnuggets.com/feed",
)

DEFAULT_REDDIT_SUBREDDITS = (
    "MachineLearning",
    "LocalLLaMA",
    "datascience",
    "ChatGPT",
)


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

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv_file()
        data_dir = Path(os.getenv("LCA_DATA_DIR", "data"))
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
            rss_feeds=_split_csv(os.getenv("LCA_RSS_FEEDS")) or DEFAULT_RSS_FEEDS,
            reddit_subreddits=_split_csv(os.getenv("LCA_REDDIT_SUBREDDITS")) or DEFAULT_REDDIT_SUBREDDITS,
            youtube_channel_ids=_split_csv(os.getenv("LCA_YOUTUBE_CHANNEL_IDS")),
            smtp=smtp,
        )

    @property
    def creator_context(self) -> str:
        return (
            "The creator has a background in data science and analytics, is transitioning "
            "into AI systems, LLMs, and agents, and wants to sound like a thinking builder "
            "who values depth, clarity, and real-world insight over hype."
        )
