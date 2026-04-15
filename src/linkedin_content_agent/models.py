from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


Decision = Literal["approved", "rejected"]
OriginalityDecision = Literal["approve", "reject"]
TransformationType = Literal["reframed", "deepened", "challenged", "applied"]


@dataclass(slots=True)
class SourceReference:
    source: str
    title: str
    url: str


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


@dataclass(slots=True)
class BackupIdea:
    title: str
    angle: str
    hook: str
    why_now: str
    visual_suggestion: str


@dataclass(slots=True)
class GeneratedContent:
    primary: PostPackage
    backups: list[BackupIdea]
    selected_topic_reason: str
    originality_audit: OriginalityAudit | None = None


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
    selected_topic: str
    status: str
    source_count: int
    delivery_status: str
    primary_artifact: str
    prompt_artifact: str
    backup_titles: list[str]
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
