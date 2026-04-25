from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import urlparse

from linkedin_content_agent.content_strategy import classify_pillar
from linkedin_content_agent.day_contracts import DayContract
from linkedin_content_agent.models import (
    DossierSource,
    EvidenceStrengthLabel,
    RunNote,
    Signal,
    SourceReference,
    SourceQuality,
    TopicCandidate,
    TopicContext,
    TopicDossier,
    TruthProfile,
)


TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "why",
    "with",
    "your",
}
REPRODUCIBLE_DOMAINS = {
    "github.com",
    "arxiv.org",
    "huggingface.co",
    "paperswithcode.com",
    "openai.com",
    "platform.openai.com",
    "docs.anthropic.com",
    "ai.google.dev",
    "developers.google.com",
}
HIGH_RISK_KEYWORDS = {
    "benchmark",
    "bias",
    "election",
    "politic",
    "policy",
    "refusal",
    "safety",
    "security",
    "jailbreak",
    "hallucination",
    "downgrade",
    "benchmark",
    "accuracy",
    "win-rate",
    "latency",
}
GENERAL_KNOWLEDGE_HINTS = {
    "mistake",
    "missing values",
    "schema",
    "pipeline",
    "null",
    "validation",
    "data cleaning",
    "feature leakage",
}
POSITIVE_MARKERS = {
    "better",
    "improved",
    "stronger",
    "faster",
    "helps",
    "works",
    "reliable",
}
NEGATIVE_MARKERS = {
    "worse",
    "downgrade",
    "failed",
    "broke",
    "refusal",
    "risk",
    "issue",
    "problem",
    "hallucination",
}
CONFLICT_MARKERS = {
    "did not replicate",
    "didn't replicate",
    "not replicate",
    "however",
    "but",
    "depends",
    "varies",
    "different",
    "in some setups",
}


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text.lower()) if len(token) > 2 and token.lower() not in STOPWORDS}


def _topic_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    if not intersection:
        return 0.0
    return intersection / max(min(len(left_tokens), len(right_tokens)), 1)


def _signal_text(signal: Signal) -> str:
    return f"{signal.title} {signal.excerpt}".strip()


def _claim_from_signal(signal: Signal) -> str:
    if signal.excerpt:
        excerpt = signal.excerpt.strip()
        if len(excerpt) > 140:
            excerpt = excerpt[:137].rstrip() + "..."
        return f"{signal.title} | {excerpt}"
    return signal.title


def _quality_from_reference(reference: SourceReference) -> SourceQuality:
    if reference.source == "run_note":
        return "first_hand"

    source_name = reference.source.lower()
    if source_name.startswith("reddit:") or source_name == "hackernews" or source_name.startswith("youtube:"):
        return "discussion"

    domain = urlparse(reference.url).netloc.lower()
    path = urlparse(reference.url).path.lower()
    if domain in REPRODUCIBLE_DOMAINS:
        return "reproducible"
    if any(marker in path for marker in ("benchmark", "eval", "paper", "docs", "research")):
        return "reproducible"
    return "technical_writeup"


def _evidence_type(reference: SourceReference, source_quality: SourceQuality) -> str:
    if source_quality == "first_hand":
        return "run_note"
    domain = urlparse(reference.url).netloc.lower()
    path = urlparse(reference.url).path.lower()
    if "github.com" in domain:
        return "repo"
    if "arxiv.org" in domain or "paper" in path:
        return "paper"
    if "docs" in path or "platform.openai.com" in domain or "docs.anthropic.com" in domain:
        return "docs"
    if "benchmark" in path or "eval" in path:
        return "benchmark"
    if source_quality == "discussion":
        return "discussion"
    return "technical_writeup"


def _confidence_for_quality(source_quality: SourceQuality, *, measured: bool = False) -> EvidenceStrengthLabel:
    if source_quality == "first_hand":
        return "strong" if measured else "medium"
    if source_quality == "reproducible":
        return "strong"
    if source_quality == "technical_writeup":
        return "medium"
    return "weak"


def load_run_notes(run_notes_dir: Path) -> list[RunNote]:
    if not run_notes_dir.exists():
        return []

    notes: list[RunNote] = []
    for path in sorted(run_notes_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        topic = str(payload.get("topic", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        if not topic or not summary:
            continue

        raw_observations = payload.get("observations", [])
        if isinstance(raw_observations, str):
            observations = [raw_observations.strip()] if raw_observations.strip() else []
        else:
            observations = [str(item).strip() for item in raw_observations if str(item).strip()]

        references: list[SourceReference] = []
        for item in payload.get("references", []):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            if not title:
                continue
            references.append(
                SourceReference(
                    source=str(item.get("source", "run_note")).strip() or "run_note",
                    title=title,
                    url=url,
                )
            )

        notes.append(
            RunNote(
                topic=topic,
                summary=summary,
                observations=observations,
                measured=bool(payload.get("measured", False)),
                created_at=str(payload.get("created_at", "")).strip() or None,
                references=references,
            )
        )
    return notes


def _match_run_note(candidate: TopicCandidate, run_notes: list[RunNote]) -> RunNote | None:
    best_note: RunNote | None = None
    best_score = 0.0
    for note in run_notes:
        score = _topic_similarity(candidate.title, note.topic)
        if candidate.title.lower() in note.summary.lower():
            score += 0.15
        if score > best_score:
            best_score = score
            best_note = note
    return best_note if best_score >= 0.35 else None


def _match_signal(reference: SourceReference, signals: list[Signal]) -> Signal | None:
    for signal in signals:
        if signal.url and signal.url == reference.url:
            return signal
    for signal in signals:
        if signal.title == reference.title:
            return signal
    return None


def _signal_to_dossier_source(signal: Signal) -> DossierSource:
    reference = signal.as_reference()
    quality = _quality_from_reference(reference)
    return DossierSource(
        reference=reference,
        source_quality=quality,
        evidence_type=_evidence_type(reference, quality),
        claim=_claim_from_signal(signal),
        confidence=_confidence_for_quality(quality),
    )


def _run_note_to_source(note: RunNote) -> DossierSource:
    reference = SourceReference(source="run_note", title=note.topic, url="")
    observation_text = " ".join(note.observations[:2]).strip()
    claim = f"{note.summary} {observation_text}".strip()
    return DossierSource(
        reference=reference,
        source_quality="first_hand",
        evidence_type="run_note",
        claim=claim,
        confidence=_confidence_for_quality("first_hand", measured=note.measured),
    )


def _related_signals(candidate: TopicCandidate, signals: list[Signal]) -> list[Signal]:
    related: list[tuple[float, Signal]] = []
    seen_urls = {reference.url for reference in candidate.supporting_signals if reference.url}

    for signal in signals:
        if signal.url in seen_urls:
            continue
        similarity = _topic_similarity(candidate.title, _signal_text(signal))
        if similarity < 0.2:
            continue
        quality = _quality_from_reference(signal.as_reference())
        quality_rank = {
            "first_hand": 4,
            "reproducible": 3,
            "technical_writeup": 2,
            "discussion": 1,
        }[quality]
        related.append((quality_rank + similarity, signal))

    related.sort(key=lambda item: item[0], reverse=True)
    return [signal for _, signal in related]


def _claim_summaries(sources: list[DossierSource]) -> list[str]:
    return [f"{source.reference.source}: {source.claim}" for source in sources]


def _infer_stance(text: str) -> str:
    normalized = text.lower()
    positive_hits = sum(marker in normalized for marker in POSITIVE_MARKERS)
    negative_hits = sum(marker in normalized for marker in NEGATIVE_MARKERS)
    conflict_hits = sum(marker in normalized for marker in CONFLICT_MARKERS)
    if conflict_hits:
        return "mixed"
    if positive_hits and not negative_hits:
        return "positive"
    if negative_hits and not positive_hits:
        return "negative"
    return "neutral"


def _consensus_and_disagreement(sources: list[DossierSource], *, weak_signal_echo: bool) -> tuple[str, list[str], str]:
    if len(sources) == 1:
        return (
            "Only one clearly relevant source matched this topic, so the post must narrow scope or frame the claim as exploratory.",
            ["This topic is effectively single-source right now."],
            "high",
        )

    stances = {_infer_stance(source.claim) for source in sources}
    stances.discard("neutral")
    disagreement_notes: list[str] = []

    if weak_signal_echo:
        disagreement_notes.append("The matched sources mostly echo discussion-level takes without a stronger technical source.")

    if "mixed" in stances or len(stances) > 1:
        disagreement_notes.append("The sources do not fully agree on the mechanism or scope of the claim.")
        return (
            "The stable angle is the disagreement itself: explain what changes across setups instead of pretending the behavior is universal.",
            disagreement_notes,
            "high",
        )

    if disagreement_notes:
        return (
            "The safest angle is a cautious synthesis with explicit provenance.",
            disagreement_notes,
            "medium",
        )

    return (
        "The sources broadly point in the same direction, so the post can interpret the pattern without overstating certainty.",
        disagreement_notes,
        "low",
    )


def _is_general_knowledge(candidate: TopicCandidate, contract: DayContract, dossier: TopicDossier) -> bool:
    if contract.day != "Tuesday":
        return False
    haystack = f"{candidate.title} {' '.join(candidate.evidence)}".lower()
    if any(marker in haystack for marker in HIGH_RISK_KEYWORDS):
        return False
    return any(marker in haystack for marker in GENERAL_KNOWLEDGE_HINTS) or dossier.stronger_source_present


def _derive_truth_profile(contract: DayContract, dossier: TopicDossier, candidate: TopicCandidate) -> TruthProfile:
    has_first_hand = any(source.source_quality == "first_hand" for source in dossier.sources)
    has_external = any(source.source_quality != "first_hand" for source in dossier.sources)
    general_knowledge = _is_general_knowledge(candidate, contract, dossier)

    if general_knowledge:
        source_ownership = "general_knowledge"
    elif has_first_hand and has_external:
        source_ownership = "mixed"
    elif has_first_hand:
        source_ownership = "first_hand"
    else:
        source_ownership = "second_hand"

    if dossier.stronger_source_present and dossier.source_count >= 3 and not dossier.weak_signal_echo and not dossier.disagreement_notes:
        evidence_strength: EvidenceStrengthLabel = "strong"
    elif dossier.source_count >= 2 and not dossier.weak_signal_echo:
        evidence_strength = "medium"
    else:
        evidence_strength = "weak"

    if any(keyword in dossier.topic_title.lower() for keyword in HIGH_RISK_KEYWORDS):
        risk_level = "high" if evidence_strength != "strong" or dossier.disagreement_notes else "medium"
    elif general_knowledge:
        risk_level = "low"
    else:
        risk_level = "medium" if evidence_strength == "medium" else "high" if evidence_strength == "weak" else "low"

    conflict_level = "high" if dossier.disagreement_notes else "low"
    if dossier.weak_signal_echo and conflict_level == "low":
        conflict_level = "medium"

    if source_ownership in {"first_hand", "mixed"} and contract.day in {"Monday", "Sunday"} and evidence_strength in {"strong", "medium"}:
        authority_mode = "builder"
    elif contract.day == "Saturday" and risk_level == "low" and conflict_level == "low":
        authority_mode = "light"
    elif conflict_level == "high" or evidence_strength == "weak":
        authority_mode = "exploratory"
    elif contract.day == "Thursday" and source_ownership == "second_hand" and not dossier.stronger_source_present:
        authority_mode = "amplifier"
    else:
        authority_mode = "applied_analyst"

    if conflict_level == "high":
        position = "test"
    elif dossier.weak_signal_echo:
        position = "challenge"
    elif evidence_strength == "strong":
        position = "support"
    else:
        position = "refine"

    if source_ownership == "first_hand":
        provenance_rule = "You may use first-person experiment language only for behaviors captured in your run note."
    elif source_ownership == "mixed":
        provenance_rule = "Say what you tested, then separate it clearly from what external sources or benchmarks contributed."
    elif source_ownership == "general_knowledge":
        provenance_rule = "Teach it as a stable practice pattern without implying a fresh benchmark or personal experiment."
    else:
        provenance_rule = "Attribute the claim to external sources in the opening lines and avoid sounding like the experiment was yours."

    if authority_mode == "builder":
        allowed_claim_posture = "Concrete first-hand explanation with clear scope, result, and lesson."
    elif authority_mode == "exploratory":
        allowed_claim_posture = "Frame the topic as a replication attempt, open question, or setup-dependent behavior."
    elif authority_mode == "amplifier":
        allowed_claim_posture = "Interpret the trend and its implication, but keep the body explicitly source-aware."
    elif authority_mode == "light":
        allowed_claim_posture = "Keep the copy light, low-risk, and grounded in a real workflow lesson."
    else:
        allowed_claim_posture = "Be bold and technical, but interpret the evidence rather than impersonating the original experiment."

    required_copy_moves = []
    if source_ownership in {"second_hand", "mixed"}:
        required_copy_moves.append("State provenance in the hook or first two lines.")
    if authority_mode == "exploratory":
        required_copy_moves.append("Signal uncertainty, replication, or open scope explicitly.")
    if contract.day in {"Wednesday", "Thursday"}:
        required_copy_moves.append("Synthesize multiple sources instead of repeating a single headline.")
    if contract.day in {"Monday", "Sunday"} and authority_mode != "builder":
        required_copy_moves.append("Use an analyst framing rather than first-person build ownership.")

    forbidden_moves = [
        "Do not present external experiments as your own.",
        "Do not generalize a single anecdote into universal system behavior.",
    ]
    if evidence_strength == "weak" or conflict_level == "high":
        forbidden_moves.append("Do not use causal or universal wording without scope limits or hedging.")
    if not dossier.stronger_source_present:
        forbidden_moves.append("Do not present discussion-level agreement as technical proof.")

    allows_first_person_experiment = source_ownership in {"first_hand", "mixed"}
    requires_explicit_provenance = source_ownership in {"second_hand", "mixed"} or authority_mode in {"amplifier", "exploratory"}
    allows_exact_metrics = source_ownership in {"first_hand", "mixed"} or (
        dossier.stronger_source_present and evidence_strength == "strong"
    )

    return TruthProfile(
        source_ownership=source_ownership,
        evidence_strength=evidence_strength,
        risk_level=risk_level,
        authority_mode=authority_mode,
        position=position,
        conflict_level=conflict_level,
        provenance_rule=provenance_rule,
        allowed_claim_posture=allowed_claim_posture,
        required_copy_moves=required_copy_moves,
        forbidden_moves=forbidden_moves,
        allows_first_person_experiment=allows_first_person_experiment,
        requires_explicit_provenance=requires_explicit_provenance,
        allows_exact_metrics=allows_exact_metrics,
    )


def build_topic_context(candidate: TopicCandidate, signals: list[Signal], contract: DayContract, run_notes: list[RunNote]) -> TopicContext:
    primary_reference = (
        candidate.supporting_signals[0]
        if candidate.supporting_signals
        else SourceReference(source="manual", title=candidate.title, url="")
    )
    primary_signal = _match_signal(primary_reference, signals)

    sources: list[DossierSource] = []
    seen_keys: set[tuple[str, str]] = set()

    if primary_signal is not None:
        dossier_source = _signal_to_dossier_source(primary_signal)
    else:
        quality = _quality_from_reference(primary_reference)
        dossier_source = DossierSource(
            reference=primary_reference,
            source_quality=quality,
            evidence_type=_evidence_type(primary_reference, quality),
            claim=primary_reference.title,
            confidence=_confidence_for_quality(quality),
        )
    sources.append(dossier_source)
    seen_keys.add((dossier_source.reference.source, dossier_source.reference.url or dossier_source.reference.title))

    matched_note = _match_run_note(candidate, run_notes)
    if matched_note is not None:
        note_source = _run_note_to_source(matched_note)
        note_key = (note_source.reference.source, note_source.reference.title)
        if note_key not in seen_keys:
            sources.append(note_source)
            seen_keys.add(note_key)

    for signal in _related_signals(candidate, signals):
        dossier_source = _signal_to_dossier_source(signal)
        key = (dossier_source.reference.source, dossier_source.reference.url or dossier_source.reference.title)
        if key in seen_keys:
            continue
        sources.append(dossier_source)
        seen_keys.add(key)
        if len(sources) >= 4:
            break

    stronger_source_present = any(source.source_quality in {"first_hand", "reproducible"} for source in sources)
    weak_signal_echo = len(sources) >= 3 and all(source.source_quality == "discussion" for source in sources)
    consensus_summary, disagreement_notes, conflict_level = _consensus_and_disagreement(sources, weak_signal_echo=weak_signal_echo)
    dossier = TopicDossier(
        topic_title=candidate.title,
        primary_signal=primary_reference,
        sources=sources,
        source_count=len(sources),
        claim_summaries=_claim_summaries(sources),
        consensus_summary=consensus_summary,
        disagreement_notes=disagreement_notes if conflict_level != "low" else [],
        stronger_source_present=stronger_source_present,
        weak_signal_echo=weak_signal_echo,
        matched_run_note=matched_note.topic if matched_note is not None else None,
    )
    return TopicContext(
        candidate=candidate,
        dossier=dossier,
        truth_profile=_derive_truth_profile(contract, dossier, candidate),
    )


def build_topic_contexts(
    candidates: list[TopicCandidate],
    signals: list[Signal],
    contract: DayContract,
    *,
    run_notes_dir: Path,
    creator_post_type: str = "insight",
    day_tone_hint: str = "",
) -> list[TopicContext]:
    run_notes = load_run_notes(run_notes_dir)
    contexts: list[TopicContext] = []
    for candidate in candidates:
        context = build_topic_context(candidate, signals, contract, run_notes)
        context.creator_post_type = creator_post_type
        context.day_tone_hint = day_tone_hint
        context.topic_pillar = classify_pillar(" ".join([candidate.title, *candidate.evidence]))
        contexts.append(context)
    return contexts
