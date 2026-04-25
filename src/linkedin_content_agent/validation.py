from __future__ import annotations

from difflib import SequenceMatcher
import re

from linkedin_content_agent.content_strategy import (
    get_banned_words,
    get_evidence_policy,
    get_originality_threshold,
    normalize_creator_post_type,
)
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
    "i measured",
    "i benchmarked",
    "my benchmark",
    "my survey",
    "in my run",
    "what broke for me",
    "in my experiment",
    "our results",
    "in my dataset",
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

PROMOTIONAL_PATTERNS = (
    "book a call",
    "dm me",
    "join my course",
    "buy now",
    "sign up today",
    "limited spots",
    "work with me",
)


def _collect_text(post: PostPackage) -> str:
    image_text = ""
    if post.image_suggestion is not None:
        image_text = " ".join(
            [
                post.image_suggestion.type,
                post.image_suggestion.description,
                post.image_suggestion.how_to_create,
                post.image_suggestion.why_it_works,
            ]
        )
    return " ".join(
        [
            post.hook,
            *post.core_idea,
            post.draft_post,
            post.visual_suggestion,
            image_text,
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


def check_readability(post_text: str) -> list[str]:
    issues: list[str] = []
    sentences = [sentence.strip() for sentence in post_text.replace("\n", ". ").split(".") if sentence.strip()]
    words = post_text.split()
    avg_sentence_length = len(words) / max(len(sentences), 1)
    banned_words = [word for word in get_banned_words() if word and word in post_text.lower()]
    long_words = [word for word in words if len(word.strip(".,!?")) > 12]

    if avg_sentence_length > 22:
        issues.append(f"Sentences are too long on average ({avg_sentence_length:.0f} words). Break them up.")
    if banned_words:
        issues.append(f"Banned corporate words found: {sorted(set(banned_words))}. Remove them.")
    if len(long_words) > 6:
        issues.append(f"The draft uses too many dense words for the target voice: {long_words[:4]}.")
    return issues


def check_provenance_explicit(post_text: str, post_type: str, topic_context: TopicContext) -> list[str]:
    policy = get_evidence_policy(post_type)
    if not policy["requires_source"]:
        if topic_context.truth_profile.authority_mode not in {"amplifier", "exploratory"}:
            return []
        if topic_context.truth_profile.risk_level == "low":
            return []
    if not _contains_any(post_text.lower(), PROVENANCE_PATTERNS):
        return ["Draft does not make source provenance explicit enough for this post type and authority mode."]
    return []


def validate_post_package(post: PostPackage, contract: DayContract, topic_context: TopicContext | None = None) -> list[str]:
    issues: list[str] = []
    combined = _collect_text(post)
    creator_post_type = normalize_creator_post_type(post.post_type)

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
    if len(EMOJI_RE.findall(post.hook + " " + post.draft_post)) > 2:
        issues.append("Contains more than two emoji characters.")
    if creator_post_type in {"insight", "commentary", "teaching"} and not any(
        marker in combined for marker in CONCRETE_MARKERS
    ) and not re.search(r"\d", combined):
        issues.append("Missing a concrete observation, technical term, or measurable detail.")
    issues.extend(check_readability(" ".join([post.hook, post.draft_post, post.why_this_works])))

    draft_lines = [line.strip() for line in post.draft_post.splitlines() if line.strip()]
    if creator_post_type == "teaching" and len(draft_lines) > 8:
        issues.append("Teaching posts should stay focused and short. Reduce the number of non-empty lines.")
    if creator_post_type == "relatable" and len(draft_lines) > 7:
        issues.append("Relatable posts should stay short and quick to scan.")

    if creator_post_type in {"insight", "commentary", "teaching"} and not any(
        token in combined for token in ("mistake", "insight", "unexpected", "tradeoff")
    ):
        issues.append("Post must include at least one mistake, insight, unexpected result, or tradeoff.")

    if contract.day in {"Saturday", "Sunday"} and _contains_any(combined, PROMOTIONAL_PATTERNS):
        issues.append("Reflective/lighter days must not be promotional or salesy.")

    if creator_post_type == "commentary" and topic_context is not None:
        headline_similarity = _headline_similarity(post.hook, topic_context.candidate.title)
        if headline_similarity >= 0.72:
            issues.append("Commentary posts cannot reuse the source headline without a real take.")

    return issues


def validate_backup_idea(backup: BackupIdea) -> list[str]:
    issues: list[str] = []
    image_text = ""
    if backup.image_suggestion is not None:
        image_text = " ".join(
            [
                backup.image_suggestion.type,
                backup.image_suggestion.description,
                backup.image_suggestion.how_to_create,
                backup.image_suggestion.why_it_works,
            ]
        )
    combined = " ".join((backup.title, backup.angle, backup.hook, backup.why_now, backup.visual_suggestion, image_text)).lower()
    if len(EMOJI_RE.findall(combined)) > 2:
        issues.append("Backup idea contains more than two emoji characters.")
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
    creator_post_type = normalize_creator_post_type(generated_content.primary.post_type)
    source_titles = _source_titles(candidate)
    hook_similarity = max(_headline_similarity(hook, title) for title in source_titles)
    claim_similarity = max(_headline_similarity(claim_text, title) for title in source_titles)
    has_mechanism = any(marker in combined for marker in DEEP_MECHANISM_MARKERS)
    threshold = get_originality_threshold(creator_post_type)

    if creator_post_type == "commentary" and hook_similarity >= 0.72:
        issues.append("Commentary hook is too similar to the source headline framing.")
    elif hook_similarity >= 0.86:
        issues.append("Hook is too similar to the source headline framing.")
    if creator_post_type in {"insight", "commentary", "teaching"} and claim_similarity >= 0.5 and not has_mechanism:
        issues.append("Draft mirrors the source claim without a distinct why/how layer.")
    if audit.originality_score < threshold:
        issues.append(f"Originality score {audit.originality_score:.2f} is below {threshold:.2f} for post type '{creator_post_type}'.")
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
    creator_post_type = normalize_creator_post_type(post.post_type)
    truth_profile = topic_context.truth_profile
    dossier = topic_context.dossier
    source_claim_text = " ".join(dossier.claim_summaries).lower()

    if truth_profile.source_ownership in {"second_hand", "general_knowledge"} and _contains_any(
        combined,
        FIRST_PERSON_EXPERIMENT_PATTERNS,
    ):
        issues.append("Draft uses first-person experiment language without first-hand evidence.")

    issues.extend(check_provenance_explicit(combined, creator_post_type, topic_context))

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
        if any(pattern in combined for pattern in ("i tested", "i benchmarked", "i measured", "in my dataset", "our results")):
            issues.append("Applied analyst mode cannot imply the creator personally ran the underlying experiment.")

    return issues


def validate_generated_content(
    generated_content: GeneratedContent,
    contract: DayContract,
    topic_context: TopicContext | None = None,
) -> list[str]:
    issues = validate_post_package(generated_content.primary, contract, topic_context)
    if len(generated_content.backups) != 2:
        issues.append("Exactly two backup ideas are required.")
    for backup in generated_content.backups:
        issues.extend(validate_backup_idea(backup))
    return issues
