from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class DayContract:
    day: str
    post_type: str
    description: str
    requirements: tuple[str, ...]
    required_signals: tuple[str, ...]
    max_lines: int | None = None


DAY_CONTRACTS: dict[str, DayContract] = {
    "Monday": DayContract(
        day="Monday",
        post_type="Build / Experiment",
        description="Show a test, comparison, or failure from practical work.",
        requirements=("what broke or what was surprising", "result", "lesson"),
        required_signals=("mistake", "unexpected result", "tradeoff", "insight"),
    ),
    "Tuesday": DayContract(
        day="Tuesday",
        post_type="Micro-Teach",
        description="Teach one small concept sharply in under ten lines.",
        requirements=("simple", "sharp", "under 10 lines"),
        required_signals=("insight",),
        max_lines=10,
    ),
    "Wednesday": DayContract(
        day="Wednesday",
        post_type="Knowledge / Carousel",
        description="Focus on mistakes, patterns, or non-obvious insights.",
        requirements=("what people get wrong", "non-obvious pattern"),
        required_signals=("mistake", "insight", "tradeoff"),
    ),
    "Thursday": DayContract(
        day="Thursday",
        post_type="AI / Industry Insight",
        description="Explain what an AI trend or tool actually changes.",
        requirements=("what this actually changes", "implications"),
        required_signals=("insight", "tradeoff"),
    ),
    "Friday": DayContract(
        day="Friday",
        post_type="Thinking / Conviction",
        description="State a strong opinion backed by reasoning.",
        requirements=("challenge a common belief", "reasoning"),
        required_signals=("tradeoff", "insight"),
    ),
    "Saturday": DayContract(
        day="Saturday",
        post_type="Thinking / Reflection",
        description="Tie a personal realization to the tech journey.",
        requirements=("how thinking evolved", "personal realization"),
        required_signals=("insight",),
    ),
    "Sunday": DayContract(
        day="Sunday",
        post_type="Build Story",
        description="Tell a human plus tech story with struggle and imperfection.",
        requirements=("struggle", "insight", "imperfection"),
        required_signals=("mistake", "insight", "unexpected result"),
    ),
}


def canonicalize_day(day: str) -> str:
    normalized = day.strip().lower()
    for candidate in DAY_CONTRACTS:
        if candidate.lower() == normalized:
            return candidate
    raise ValueError(f"Unsupported day override: {day!r}")


def resolve_day_contract(
    day_override: str | None = None,
    *,
    now: datetime | None = None,
    timezone: str = "Africa/Lagos",
) -> DayContract:
    if day_override:
        return DAY_CONTRACTS[canonicalize_day(day_override)]

    if now is not None:
        current = now
    else:
        try:
            current = datetime.now(ZoneInfo(timezone))
        except ZoneInfoNotFoundError:
            current = datetime.now(UTC)
    return DAY_CONTRACTS[current.strftime("%A")]


def resolve_topic_choice(topic_override: str | None, fallback_title: str) -> str:
    if topic_override and topic_override.strip():
        return topic_override.strip()
    return fallback_title
