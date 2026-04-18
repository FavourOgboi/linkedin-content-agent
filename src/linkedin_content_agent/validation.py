from __future__ import annotations

from difflib import SequenceMatcher
import re

from linkedin_content_agent.day_contracts import DayContract
from linkedin_content_agent.models import BackupIdea, GeneratedContent, OriginalityAudit, PostPackage, TopicCandidate, TopicContext


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

DEEP_MECHANISM_MARKERS = (
    "because",
    "how",
    "why",
    "due to",
    "causes",
    "caused",
    "break",
    "breaks",
    "broke",
    "system",
    "workflow",
    "pipeline",
    "protocol",
    "contract",
    "boundary",
    "failure mode",
    "production",
    "operational",
    "adherence",
)

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
METRIC_RE = re.compile(
    r"(\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?x\b|\b\d+(?:\.\d+)?\s?(?:ms|s|sec|secs|seconds|minutes|tokens?)\b)",
    re.IGNORECASE,
)
MODEL_NAME_RE = re.compile(r"\b(?:gpt|claude|gemini|llama|mistral|o\d+)[- ]?[a-z0-9\.]+\b", re.IGNORECASE)

FIRST_PERSON_EXPERIMENT_PATTERNS = (
    "i tested",
    "i ran",
    "in my run",
    "i built",
    "what broke for me",
    "i expected",
    "i tried using",
    "my experiment",
)

PROVENANCE_PATTERNS = (
    "a recent benchmark",
    "a recent experiment",
    "a recent repo",
    "a recent writeup",
    "an external experiment",
    "a benchmark suggests",
    "across a few sources",
    "across a few discussions",
    "according to",
    "i came across",
    "worth testing",
    "i tried to replicate",
    "a recent github experiment",
)

HEDGE_PATTERNS = (
    "suggests",
    "may",
    "might",
    "can",
    "seems",
    "appears",
    "in some setups",
    "in one benchmark",
    "across a few examples",
    "setup-dependent",
    "not universal",
    "worth testing",
)

UNIVERSAL_PATTERNS = (
    "always",
    "never",
    "every",
    "everyone",
    "nobody",
    "100%",
    "guarantees",
    "proves",
    "all teams",
    "all models",
)

CAUSAL_PATTERNS = (
    "causes",
    "caused",
    "turned",
    "makes",
    "breaks",
    "shows that",
    "means that",
)

SATURDAY_EVOLUTION_PATTERNS = (
    "i used to think",
    "changed my mind",
    "thinking evolved",
    "i now think",
    "i now assume",
    "i've started",
    "i have started",
    "i started treating",
    "i now treat",
    "my mental model changed",
    "i used to read",
    "i no longer assume",
    "that changed how i",
)


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


def _tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def _headline_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    token_similarity = 0.0
    if left_tokens and right_tokens:
        token_similarity = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    string_similarity = SequenceMatcher(None, left.lower(), right.lower()).ratio()
    return max(token_similarity, string_similarity)


def _source_titles(candidate: TopicCandidate) -> list[str]:
    titles = [reference.title for reference in candidate.supporting_signals if reference.title]
    return titles or [candidate.title]


def fallback_originality_audit(candidate: TopicCandidate, generated_content: GeneratedContent) -> OriginalityAudit:
    combined = _collect_text(generated_content.primary)
    source_signal = _source_titles(candidate)[0]
    similarity = max(_headline_similarity(generated_content.primary.hook, title) for title in _source_titles(candidate))
    has_mechanism = any(marker in combined for marker in DEEP_MECHANISM_MARKERS)
    originality_score = 8.0 if has_mechanism and similarity < 0.7 else 4.5 if has_mechanism else 3.0
    decision = "approve" if originality_score >= 7.0 else "reject"
    transformation_type = "deepened" if has_mechanism else "reframed"
    new_insight = (
        "The draft explains the deeper system mechanism behind the source signal."
        if has_mechanism
        else "Add a deeper mechanism, contradiction, or applied system explanation beyond the source framing."
    )
    return OriginalityAudit(
        source_signal=source_signal,
        core_claim_from_source=candidate.title,
        transformation_type=transformation_type,
        new_mechanism_or_insight=new_insight,
        originality_score=round(originality_score, 2),
        decision=decision,
    )


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
        if not any(token in combined for token in SATURDAY_EVOLUTION_PATTERNS):
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


def validate_originality(
    generated_content: GeneratedContent,
    candidate: TopicCandidate,
    audit: OriginalityAudit,
) -> list[str]:
    issues: list[str] = []
    combined = _collect_text(generated_content.primary)
    hook = generated_content.primary.hook
    claim_text = " ".join([generated_content.primary.hook, *generated_content.primary.core_idea[:2]])
    source_titles = _source_titles(candidate)
    hook_similarity = max(_headline_similarity(hook, title) for title in source_titles)
    claim_similarity = max(_headline_similarity(claim_text, title) for title in source_titles)
    has_mechanism = any(marker in combined for marker in DEEP_MECHANISM_MARKERS)

    if hook_similarity >= 0.72:
        issues.append("Hook is too similar to the source headline framing.")
    if claim_similarity >= 0.5 and not has_mechanism:
        issues.append("Draft mirrors the source claim without a distinct why/how layer.")
    if audit.originality_score < 7.0:
        issues.append("Originality score is below 7.")
    if audit.decision != "approve":
        issues.append("Originality audit rejected the draft.")
    if not audit.new_mechanism_or_insight.strip():
        issues.append("Originality audit did not provide a new mechanism or insight.")

    return issues


def _model_mentions(text: str) -> set[str]:
    return {match.group(0).lower() for match in MODEL_NAME_RE.finditer(text)}


def validate_truth_alignment(
    generated_content: GeneratedContent,
    contract: DayContract,
    topic_context: TopicContext,
) -> list[str]:
    issues: list[str] = []
    post = generated_content.primary
    combined = _collect_text(post)
    truth_profile = topic_context.truth_profile
    dossier = topic_context.dossier
    source_claim_text = " ".join(dossier.claim_summaries).lower()

    if truth_profile.source_ownership in {"second_hand", "general_knowledge"}:
        if _contains_any(combined, FIRST_PERSON_EXPERIMENT_PATTERNS):
            issues.append("Draft uses first-person experiment language without first-hand evidence.")

    if truth_profile.requires_explicit_provenance and not _contains_any(combined, PROVENANCE_PATTERNS):
        issues.append("Draft does not make source provenance explicit enough for the assigned authority mode.")

    if not truth_profile.allows_exact_metrics and METRIC_RE.search(combined):
        issues.append("Draft includes exact metrics without dossier support.")

    if dossier.weak_signal_echo and dossier.source_count >= 3:
        issues.append("Topic relies on echoing low-quality sources without stronger technical support.")

    if truth_profile.authority_mode == "exploratory":
        exploratory_markers = ("?", "worth testing", "i tried to replicate", "open question", "still testing", "not convinced")
        if not any(marker in combined for marker in exploratory_markers):
            issues.append("Exploratory posts must signal uncertainty, replication, or open scope.")

    if truth_profile.authority_mode == "light":
        high_risk_terms = ("benchmark", "bias", "politic", "safety", "security", "refusal")
        if any(term in combined for term in high_risk_terms):
            issues.append("Light posts cannot carry high-risk benchmark, safety, or political claims.")

    if contract.day in {"Monday", "Sunday"} and truth_profile.authority_mode != "builder" and _contains_any(
        combined,
        FIRST_PERSON_EXPERIMENT_PATTERNS,
    ):
        issues.append("This day was downgraded from Builder authority, so the draft cannot sound first-hand.")

    if truth_profile.risk_level == "high" or truth_profile.evidence_strength == "weak" or truth_profile.conflict_level == "high":
        if (_contains_any(combined, UNIVERSAL_PATTERNS) or _contains_any(combined, CAUSAL_PATTERNS)) and not _contains_any(
            combined,
            HEDGE_PATTERNS,
        ):
            issues.append("High-risk or weak-evidence drafts need hedging or scope limits before making causal or universal claims.")

    mentioned_models = _model_mentions(combined)
    allowed_models = _model_mentions(source_claim_text)
    unknown_models = mentioned_models - allowed_models
    if unknown_models:
        issues.append("Draft references model names or versions not present in the supporting dossier.")

    if truth_profile.authority_mode == "applied_analyst" and truth_profile.source_ownership == "second_hand":
        if "i tested" in combined or "i built" in combined:
            issues.append("Applied analyst mode cannot imply the creator personally ran the underlying experiment.")

    return issues


def validate_generated_content(generated_content: GeneratedContent, contract: DayContract) -> list[str]:
    issues = validate_post_package(generated_content.primary, contract)
    if len(generated_content.backups) != 2:
        issues.append("Exactly two backup ideas are required.")
    for backup in generated_content.backups:
        issues.extend(validate_backup_idea(backup))
    return issues
