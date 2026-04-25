from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


Decision = Literal["approved", "rejected"]
OriginalityDecision = Literal["approve", "reject"]
TransformationType = Literal["reframed", "deepened", "challenged", "applied"]
SourceOwnership = Literal["first_hand", "mixed", "second_hand", "general_knowledge"]
EvidenceStrengthLabel = Literal["strong", "medium", "weak"]
RiskLevel = Literal["low", "medium", "high"]
AuthorityMode = Literal["builder", "applied_analyst", "amplifier", "exploratory", "light"]
PositionType = Literal["support", "challenge", "refine", "test"]
SourceQuality = Literal["first_hand", "reproducible", "technical_writeup", "discussion"]
ConflictLevel = Literal["low", "medium", "high"]
CreatorPostType = Literal["insight", "relatable", "commentary", "teaching", "inspiration"]
TopicPillar = Literal["ai_ml", "data_engineering", "python_backend", "beginner_practice", "career_insight", ""]
ContentFormat = Literal["text", "photo", "screenshot", "carousel", "infographic"]
LengthMode = Literal["standard", "extended"]
CommentSentiment = Literal["excited", "skeptical", "divided", "practical", "unknown"]
CommentSignalStrength = Literal["low", "medium", "high"]
CommentUsageMode = Literal["angle_driver", "nuance_layer", "example_source", "tone_signal", "ignore"]


@dataclass(slots=True)
class SourceReference:
    source: str
    title: str
    url: str


@dataclass(slots=True)
class RunNote:
    topic: str
    summary: str
    observations: list[str]
    measured: bool = False
    created_at: str | None = None
    references: list[SourceReference] = field(default_factory=list)


@dataclass(slots=True)
class Signal:
    source: str
    title: str
    url: str
    published_at: str | None
    engagement_hint: dict[str, Any]
    excerpt: str
    raw_metadata: dict[str, Any]

    def as_reference(self) -> SourceReference:
        return SourceReference(source=self.source, title=self.title, url=self.url)


@dataclass(slots=True)
class ScoreBreakdown:
    source_weight: float
    recency: float
    relevance: float
    evidence_strength: float
    novelty_penalty: float
    total: float


@dataclass(slots=True)
class TopicCandidate:
    title: str
    score_total: float
    score_breakdown: ScoreBreakdown
    day_fit: str
    evidence: list[str]
    angles: list[str]
    novelty_penalty: float
    supporting_signals: list[SourceReference] = field(default_factory=list)


@dataclass(slots=True)
class DossierSource:
    reference: SourceReference
    source_quality: SourceQuality
    evidence_type: str
    claim: str
    confidence: EvidenceStrengthLabel


@dataclass(slots=True)
class TopicDossier:
    topic_title: str
    primary_signal: SourceReference
    sources: list[DossierSource]
    source_count: int
    claim_summaries: list[str]
    consensus_summary: str
    disagreement_notes: list[str]
    stronger_source_present: bool
    weak_signal_echo: bool
    matched_run_note: str | None = None


@dataclass(slots=True)
class TruthProfile:
    source_ownership: SourceOwnership
    evidence_strength: EvidenceStrengthLabel
    risk_level: RiskLevel
    authority_mode: AuthorityMode
    position: PositionType
    conflict_level: ConflictLevel
    provenance_rule: str
    allowed_claim_posture: str
    required_copy_moves: list[str]
    forbidden_moves: list[str]
    allows_first_person_experiment: bool
    requires_explicit_provenance: bool
    allows_exact_metrics: bool


@dataclass(slots=True)
class CommentInsight:
    source: str
    comment_count: int
    top_sentiment: CommentSentiment
    signal_strength: CommentSignalStrength
    key_debates: list[str]
    strongest_pushback: str
    common_question: str


@dataclass(slots=True)
class TopicContext:
    candidate: TopicCandidate
    dossier: TopicDossier
    truth_profile: TruthProfile
    creator_post_type: CreatorPostType = "insight"
    day_tone_hint: str = ""
    topic_pillar: TopicPillar = ""
    content_format: ContentFormat = "text"
    comment_insight: CommentInsight | None = None
    comment_usage_mode: CommentUsageMode = "ignore"


@dataclass(slots=True)
class SelfAudit:
    passed_checks: list[str]
    critic_notes: list[str]


@dataclass(slots=True)
class OriginalityAudit:
    source_signal: str
    core_claim_from_source: str
    transformation_type: TransformationType
    new_mechanism_or_insight: str
    originality_score: float
    decision: OriginalityDecision


@dataclass(slots=True)
class ImageSuggestion:
    type: str
    description: str
    how_to_create: str
    why_it_works: str


@dataclass(slots=True)
class CarouselSlide:
    title: str
    bullets: list[str]


@dataclass(slots=True)
class FormatPlan:
    format: ContentFormat
    what_to_create: str
    why_this_format: str
    asset_brief: list[str]
    deadline_hint: str
    caption_note: str
    visual_structure: str | None = None
    slides: list[CarouselSlide] | None = None


@dataclass(slots=True)
class PostPackage:
    day: str
    post_type: str
    hook: str
    core_idea: list[str]
    draft_post: str
    visual_suggestion: str
    why_this_works: str
    source_refs: list[SourceReference]
    self_audit: SelfAudit
    image_suggestion: ImageSuggestion | None = None
    length_mode: LengthMode = "standard"
    length_mode_reason: str | None = None


@dataclass(slots=True)
class BackupIdea:
    title: str
    angle: str
    hook: str
    why_now: str
    visual_suggestion: str
    image_suggestion: ImageSuggestion | None = None


@dataclass(slots=True)
class GeneratedContent:
    primary: PostPackage
    backups: list[BackupIdea]
    selected_topic_reason: str
    originality_audit: OriginalityAudit | None = None
    topic_dossier: TopicDossier | None = None
    truth_profile: TruthProfile | None = None
    format_plan: FormatPlan | None = None
    backup_text_post: PostPackage | None = None
    comment_insight: CommentInsight | None = None
    comment_usage_mode: CommentUsageMode = "ignore"
    audit_skipped: bool = False
    audit_skip_reason: str | None = None


@dataclass(slots=True)
class TopicSelection:
    selected_title: str
    selected_reason: str
    backup_titles: list[str]
    caution_notes: list[str]


@dataclass(slots=True)
class ReviewRecord:
    run_id: str
    decision: Decision
    notes: str
    decided_at: str


@dataclass(slots=True)
class RunSummary:
    run_id: str
    created_at: str
    day: str
    post_type: str
    creator_post_type: CreatorPostType | str
    topic_pillar: TopicPillar | str
    content_format: ContentFormat | str
    selected_topic: str
    status: str
    source_count: int
    delivery_status: str
    primary_artifact: str
    prompt_artifact: str
    backup_titles: list[str]
    comment_insight_used: bool = False
    audit_skipped: bool = False
    audit_skip_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EmailPayload:
    subject: str
    body_text: str
    recipient: str


@dataclass(slots=True)
class DeliveryResult:
    status: str
    detail: str


@dataclass(slots=True)
class ModelAuditResult:
    passed: bool
    reasons: list[str]
    revision_instructions: str


@dataclass(slots=True)
class RunOptions:
    day_override: str | None = None
    topic_override: str | None = None
    post_type_override: CreatorPostType | None = None
    format_override: ContentFormat | None = None
    send_email: bool = True


@dataclass(slots=True)
class RunArtifacts:
    json_path: Path
    markdown_path: Path
    prompt_path: Path
    sqlite_path: Path


@dataclass(slots=True)
class AgentRunResult:
    summary: RunSummary
    generated_content: GeneratedContent
    candidates: list[TopicCandidate]
    signals: list[Signal]
    warnings: list[str]
    artifacts: RunArtifacts
    delivery_result: DeliveryResult

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunContext:
    run_id: str
    created_at: datetime
    day: str
    post_type: str
    creator_post_type: CreatorPostType | str = ""
    content_format: ContentFormat | str = "text"
