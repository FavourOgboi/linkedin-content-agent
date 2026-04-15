from __future__ import annotations

import re

from linkedin_content_agent.day_contracts import DayContract
from linkedin_content_agent.models import BackupIdea, GeneratedContent, PostPackage


HYPE_PATTERNS = (
    "game changer",
    "revolutionary",
    "crush it",
    "next-level",
    "unlock massive",
)

MOTIVATIONAL_PATTERNS = (
    "build your dreams",
    "launch faster",
    "create without limits",
    "sky is the limit",
)

BASIC_EXPLANATION_PATTERNS = (
    "what is ",
    "basically",
    "in simple terms",
    "let's break it down",
)

CONCRETE_MARKERS = (
    "llm",
    "agent",
    "workflow",
    "latency",
    "cost",
    "eval",
    "schema",
    "dataset",
    "pipeline",
    "token",
    "retrieval",
    "benchmark",
    "compare",
    "tradeoff",
)

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _collect_text(post: PostPackage) -> str:
    return " ".join(
        [
            post.hook,
            *post.core_idea,
            post.draft_post,
            post.visual_suggestion,
            post.why_this_works,
            *post.self_audit.passed_checks,
            *post.self_audit.critic_notes,
        ]
    ).lower()


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def validate_post_package(post: PostPackage, contract: DayContract) -> list[str]:
    issues: list[str] = []
    combined = _collect_text(post)

    if not post.hook.strip():
        issues.append("Hook is empty.")
    if len(post.core_idea) < 3 or len(post.core_idea) > 5:
        issues.append("Core idea must contain 3 to 5 bullets.")
    if not post.source_refs:
        issues.append("At least one source reference is required.")
    if not post.self_audit.passed_checks:
        issues.append("Self audit must include passed checks.")

    if _contains_any(combined, HYPE_PATTERNS):
        issues.append("Contains banned hype language.")
    if _contains_any(combined, MOTIVATIONAL_PATTERNS):
        issues.append("Contains vague motivational language.")
    if _contains_any(combined, BASIC_EXPLANATION_PATTERNS):
        issues.append("Contains basic explanatory filler.")
    if EMOJI_RE.search(combined):
        issues.append("Contains emoji characters.")
    if not any(marker in combined for marker in CONCRETE_MARKERS) and not re.search(r"\d", combined):
        issues.append("Missing a concrete observation, technical term, or measurable detail.")

    draft_lines = [line.strip() for line in post.draft_post.splitlines() if line.strip()]
    if contract.max_lines is not None and len(draft_lines) > contract.max_lines:
        issues.append(f"{contract.day} posts must stay under {contract.max_lines} non-empty lines.")

    if contract.day == "Monday":
        if not any(token in combined for token in ("broke", "failed", "surpris", "unexpected")):
            issues.append("Monday post must mention what broke or what was surprising.")
        if not any(token in combined for token in ("lesson", "learned", "result")):
            issues.append("Monday post must include a result and lesson.")
    elif contract.day == "Wednesday":
        if "people get wrong" not in combined and "mistake" not in combined:
            issues.append("Wednesday post must state what people get wrong.")
    elif contract.day == "Thursday":
        if "what this actually changes" not in combined and "this changes" not in combined:
            issues.append("Thursday post must explain what this actually changes.")
        if "implication" not in combined and "means" not in combined:
            issues.append("Thursday post must include implications.")
    elif contract.day == "Friday":
        if not any(token in combined for token in ("common belief", "most people", "popular advice", "i disagree", "we should stop")):
            issues.append("Friday post must challenge a common belief.")
    elif contract.day == "Saturday":
        if not any(token in combined for token in ("i used to think", "changed my mind", "thinking evolved", "i now think")):
            issues.append("Saturday post must show how thinking evolved.")
    elif contract.day == "Sunday":
        if "struggle" not in combined and "hard part" not in combined:
            issues.append("Sunday post must include struggle.")
        if "insight" not in combined and "learned" not in combined:
            issues.append("Sunday post must include insight.")

    if not any(token in combined for token in ("mistake", "insight", "unexpected", "tradeoff")):
        issues.append("Post must include at least one mistake, insight, unexpected result, or tradeoff.")

    return issues


def validate_backup_idea(backup: BackupIdea) -> list[str]:
    issues: list[str] = []
    combined = " ".join((backup.title, backup.angle, backup.hook, backup.why_now, backup.visual_suggestion)).lower()
    if EMOJI_RE.search(combined):
        issues.append("Backup idea contains emoji characters.")
    if _contains_any(combined, HYPE_PATTERNS):
        issues.append("Backup idea contains banned hype language.")
    return issues


def validate_generated_content(generated_content: GeneratedContent, contract: DayContract) -> list[str]:
    issues = validate_post_package(generated_content.primary, contract)
    if len(generated_content.backups) != 2:
        issues.append("Exactly two backup ideas are required.")
    for backup in generated_content.backups:
        issues.extend(validate_backup_idea(backup))
    return issues
