from __future__ import annotations

from datetime import UTC, datetime
import math
import re

from linkedin_content_agent.day_contracts import DayContract
from linkedin_content_agent.models import ScoreBreakdown, Signal, TopicCandidate
from linkedin_content_agent.utils import parse_iso_datetime, unique_preserve_order


RELEVANCE_KEYWORDS = {
    "ai",
    "agent",
    "agentic",
    "agents",
    "assistant",
    "assistants",
    "benchmark",
    "chunking",
    "llm",
    "llms",
    "mcp",
    "embedding",
    "embeddings",
    "vector",
    "vectors",
    "rag",
    "workflow",
    "workflows",
    "automation",
    "eval",
    "evaluation",
    "guardrail",
    "guardrails",
    "hallucination",
    "hallucinations",
    "retrieval",
    "reasoning",
    "prompt",
    "prompts",
    "inference",
    "schema",
    "security",
    "tool",
    "tools",
    "dataset",
    "data",
    "analytics",
    "analysis",
    "sql",
    "python",
    "pandas",
    "api",
    "backend",
    "excel",
    "dashboard",
    "airflow",
    "dbt",
    "warehouse",
    "debugging",
    "interview",
    "career",
    "model",
    "models",
    "tooling",
    "observability",
    "pipeline",
}

ANGLE_KEYWORDS = {
    "mistake": {"mistake", "wrong", "pitfall", "failed", "failure", "bug", "broke"},
    "unexpected result": {"surprise", "surprising", "unexpected", "counterintuitive"},
    "tradeoff": {"tradeoff", "trade-off", "versus", "vs", "cost", "latency", "overhead", "compromise"},
    "insight": {"lesson", "learned", "insight", "pattern", "why", "because"},
}

SOURCE_WEIGHTS = {
    "reddit": 1.0,
    "youtube": 0.9,
    "hackernews": 0.8,
    "rss": 0.65,
}

LLM_BENCHMARK_TERMS = (
    "benchmark",
    "beats gpt",
    "outperforms",
    "llm leaderboard",
    "model release",
    "new model",
    "parameter",
    "sota",
)


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower()))


def _source_weight(source: str) -> float:
    if source.startswith("reddit:"):
        return SOURCE_WEIGHTS["reddit"]
    if source.startswith("youtube:"):
        return SOURCE_WEIGHTS["youtube"]
    if source == "hackernews":
        return SOURCE_WEIGHTS["hackernews"]
    return SOURCE_WEIGHTS["rss"]


def derive_angles(signal: Signal) -> list[str]:
    haystack = f"{signal.title} {signal.excerpt}".lower()
    angles = [label for label, keywords in ANGLE_KEYWORDS.items() if any(keyword in haystack for keyword in keywords)]

    if not angles:
        relevance_hits = len(tokenize(haystack) & RELEVANCE_KEYWORDS)
        if relevance_hits >= 2:
            angles.append("insight")

    return unique_preserve_order(angles)


def recency_score(signal: Signal, *, now: datetime | None = None) -> float:
    current = now or datetime.now(UTC)
    parsed = parse_iso_datetime(signal.published_at)
    if parsed is None:
        return 0.25
    age_hours = max((current - parsed).total_seconds() / 3600.0, 0.0)
    return max(0.0, 1.0 - min(age_hours / 168.0, 1.0))


def relevance_score(signal: Signal) -> float:
    tokens = tokenize(f"{signal.title} {signal.excerpt}")
    overlap = len(tokens & RELEVANCE_KEYWORDS)
    return min(overlap / 8.0, 1.0)


def evidence_strength(signal: Signal) -> float:
    excerpt_score = min(len(signal.excerpt.split()) / 80.0, 0.5)
    engagement = signal.engagement_hint
    score = 0.25 + excerpt_score

    score_value = float(engagement.get("score", 0) or 0)
    comments_value = float(engagement.get("num_comments", 0) or 0)
    if score_value:
        score += min(math.log1p(score_value) / 10.0, 0.25)
    if comments_value:
        score += min(math.log1p(comments_value) / 10.0, 0.25)
    return min(score, 1.0)


def novelty_penalty(title: str, prior_titles: list[str]) -> float:
    current_tokens = tokenize(title)
    highest_similarity = 0.0
    for prior in prior_titles:
        prior_tokens = tokenize(prior)
        if not current_tokens or not prior_tokens:
            continue
        similarity = len(current_tokens & prior_tokens) / len(current_tokens | prior_tokens)
        highest_similarity = max(highest_similarity, similarity)
    return round(highest_similarity * 0.4, 4)


def day_fit_label(contract: DayContract, signal: Signal, angles: list[str]) -> str:
    if any(required in angles for required in contract.required_signals):
        return "strong"
    if "insight" in angles:
        return "moderate"
    return "weak"


def llm_benchmark_penalty(signal: Signal) -> float:
    haystack = f"{signal.title} {signal.excerpt}".lower()
    matches = sum(1 for term in LLM_BENCHMARK_TERMS if term in haystack)
    return 0.3 if matches >= 2 else 0.0


def build_candidate(signal: Signal, contract: DayContract, prior_titles: list[str]) -> TopicCandidate | None:
    angles = derive_angles(signal)
    if not angles:
        return None

    source_component = _source_weight(signal.source)
    recency_component = recency_score(signal)
    relevance_component = relevance_score(signal)
    if relevance_component <= 0.0:
        return None
    evidence_component = evidence_strength(signal)
    novelty_component = novelty_penalty(signal.title, prior_titles)
    release_chasing_penalty = llm_benchmark_penalty(signal)

    day_bonus = 0.2 if any(angle in contract.required_signals for angle in angles) else 0.0
    total = round(
        source_component
        + recency_component
        + relevance_component
        + evidence_component
        + day_bonus
        - novelty_component
        - release_chasing_penalty,
        4,
    )
    evidence = [
        f"Source: {signal.source}",
        f"Headline: {signal.title}",
    ]
    if signal.excerpt:
        evidence.append(f"Excerpt: {signal.excerpt[:180]}")
    if signal.engagement_hint:
        evidence.append(f"Engagement: {signal.engagement_hint}")

    breakdown = ScoreBreakdown(
        source_weight=round(source_component, 4),
        recency=round(recency_component, 4),
        relevance=round(relevance_component, 4),
        evidence_strength=round(evidence_component, 4),
        novelty_penalty=round(novelty_component, 4),
        total=total,
    )
    return TopicCandidate(
        title=signal.title,
        score_total=total,
        score_breakdown=breakdown,
        day_fit=day_fit_label(contract, signal, angles),
        evidence=evidence,
        angles=angles,
        novelty_penalty=breakdown.novelty_penalty,
        supporting_signals=[signal.as_reference()],
    )


def rank_signals(
    signals: list[Signal],
    contract: DayContract,
    *,
    prior_titles: list[str],
    limit: int = 12,
) -> list[TopicCandidate]:
    candidates = [
        candidate
        for signal in signals
        if (candidate := build_candidate(signal, contract, prior_titles)) is not None
    ]
    candidates.sort(
        key=lambda candidate: (
            candidate.score_total,
            candidate.score_breakdown.relevance,
            candidate.score_breakdown.recency,
        ),
        reverse=True,
    )
    return candidates[:limit]
