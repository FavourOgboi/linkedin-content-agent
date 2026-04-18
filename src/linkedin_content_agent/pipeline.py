from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from linkedin_content_agent.config import AppConfig
from linkedin_content_agent.day_contracts import resolve_day_contract, resolve_topic_choice
from linkedin_content_agent.emailer import SMTPEmailSender
from linkedin_content_agent.models import DeliveryResult, OriginalityAudit, ReviewRecord, RunOptions, TopicCandidate, TopicContext, TopicSelection
from linkedin_content_agent.models import AgentRunResult, RunContext
from linkedin_content_agent.openai_client import ContentModel, OpenAIContentModel
from linkedin_content_agent.rendering import render_email_payload
from linkedin_content_agent.scoring import rank_signals
from linkedin_content_agent.sources.base import safe_fetch
from linkedin_content_agent.sources.catalog import build_default_sources
from linkedin_content_agent.storage import LocalHybridStorage, StorageBackend
from linkedin_content_agent.truth_engine import build_topic_contexts
from linkedin_content_agent.utils import slugify, utc_now
from linkedin_content_agent.validation import (
    fallback_originality_audit,
    validate_generated_content,
    validate_originality,
    validate_truth_alignment,
)


class ContentAgent:
    def __init__(
        self,
        *,
        config: AppConfig,
        storage: StorageBackend,
        model: ContentModel,
        email_sender: SMTPEmailSender,
        source_adapters: list[object],
    ) -> None:
        self.config = config
        self.storage = storage
        self.model = model
        self.email_sender = email_sender
        self.source_adapters = source_adapters

    @classmethod
    def from_config(cls, config: AppConfig) -> "ContentAgent":
        return cls(
            config=config,
            storage=LocalHybridStorage(config.data_dir),
            model=OpenAIContentModel(config),
            email_sender=SMTPEmailSender(config.smtp),
            source_adapters=build_default_sources(config),
        )

    def run(self, options: RunOptions) -> AgentRunResult:
        try:
            now = datetime.now(ZoneInfo(self.config.timezone))
        except ZoneInfoNotFoundError:
            now = datetime.now(UTC)
        contract = resolve_day_contract(options.day_override, now=now, timezone=self.config.timezone)
        context = RunContext(
            run_id=f"{now.strftime('%Y%m%d-%H%M%S')}-{slugify(contract.day)}",
            created_at=now,
            day=contract.day,
            post_type=contract.post_type,
        )

        warnings: list[str] = []
        signals = self._collect_signals(warnings)
        prior_titles = self.storage.load_recent_topic_titles()
        candidates = rank_signals(signals, contract, prior_titles=prior_titles)

        if not candidates and not options.topic_override:
            raise RuntimeError("No viable topic candidates were generated from the public signal set.")

        if options.topic_override and all(candidate.title != options.topic_override.strip() for candidate in candidates):
            candidates = [self._manual_candidate(options.topic_override.strip(), signals)] + candidates

        topic_contexts = build_topic_contexts(
            candidates,
            signals,
            contract,
            run_notes_dir=self.config.run_notes_dir,
        )
        if not topic_contexts and not options.topic_override:
            raise RuntimeError("No viable topic dossiers were generated from the public signal set.")

        selection = self.model.choose_topic(contract, topic_contexts, options.topic_override)
        selected_topic = resolve_topic_choice(options.topic_override, selection.selected_title)
        effective_selection = TopicSelection(
            selected_title=selected_topic,
            selected_reason=selection.selected_reason,
            backup_titles=selection.backup_titles,
            caution_notes=selection.caution_notes,
        )

        generated_content, accepted_selection = self._generate_with_truth_and_originality_guard(
            contract,
            effective_selection,
            topic_contexts,
        )
        selected_topic = accepted_selection.selected_title
        review_url = self._review_url(context.run_id)
        prompt_payload = {
            "run_id": context.run_id,
            "contract": asdict(contract),
            "initial_selection": asdict(effective_selection),
            "final_selection": asdict(accepted_selection),
            "truth_profile": asdict(generated_content.truth_profile) if generated_content.truth_profile is not None else None,
            "topic_dossier": asdict(generated_content.topic_dossier) if generated_content.topic_dossier is not None else None,
            "originality_audit": (
                asdict(generated_content.originality_audit) if generated_content.originality_audit is not None else None
            ),
            "topic_contexts": [asdict(context) for context in topic_contexts[:5]],
            "signal_count": len(signals),
        }
        delivery_result = self._deliver(context, generated_content, selected_topic, review_url, options.send_email)
        summary, artifacts = self.storage.save_run(
            context=context,
            selected_topic=selected_topic,
            generated_content=generated_content,
            candidates=[context.candidate for context in topic_contexts],
            signals=signals,
            delivery_result=delivery_result,
            warnings=warnings,
            prompt_payload=prompt_payload,
            review_url=review_url,
        )
        return AgentRunResult(
            summary=summary,
            generated_content=generated_content,
            candidates=[context.candidate for context in topic_contexts],
            signals=signals,
            warnings=warnings,
            artifacts=artifacts,
            delivery_result=delivery_result,
        )

    def _collect_signals(self, warnings: list[str]) -> list[object]:
        signals: list[object] = []
        for adapter in self.source_adapters:
            fetched, error = safe_fetch(adapter)
            signals.extend(fetched)
            if error:
                warnings.append(error)
        return signals

    def _manual_candidate(self, selected_topic: str, signals: list[object]) -> TopicCandidate:
        from linkedin_content_agent.models import ScoreBreakdown

        supporting = [signal.as_reference() for signal in signals[:3] if hasattr(signal, "as_reference")]
        return TopicCandidate(
            title=selected_topic,
            score_total=0.0,
            score_breakdown=ScoreBreakdown(
                source_weight=0.0,
                recency=0.0,
                relevance=0.0,
                evidence_strength=0.0,
                novelty_penalty=0.0,
                total=0.0,
            ),
            day_fit="manual_override",
            evidence=["Manual topic override supplied by the operator."],
            angles=["insight"],
            novelty_penalty=0.0,
            supporting_signals=supporting,
        )

    def _topic_context_queue(self, selection: TopicSelection, topic_contexts: list[TopicContext]) -> list[TopicContext]:
        ordered_titles = [selection.selected_title, *selection.backup_titles]
        queued: list[TopicContext] = []
        seen_titles: set[str] = set()

        for title in ordered_titles:
            for topic_context in topic_contexts:
                candidate = topic_context.candidate
                if candidate.title == title and candidate.title not in seen_titles:
                    queued.append(topic_context)
                    seen_titles.add(candidate.title)
                    break

        for topic_context in topic_contexts:
            candidate = topic_context.candidate
            if candidate.title in seen_titles:
                continue
            queued.append(topic_context)
            seen_titles.add(candidate.title)

        return queued

    def _selection_for_candidate(
        self,
        selection: TopicSelection,
        topic_context: TopicContext,
        *,
        prior_rejections: list[str],
    ) -> TopicSelection:
        candidate = topic_context.candidate
        if candidate.title == selection.selected_title and not prior_rejections:
            return selection

        reason = (
            f"Fallback after truth/originality rejection of: {', '.join(prior_rejections)}."
            if prior_rejections
            else selection.selected_reason
        )
        backups = [title for title in selection.backup_titles if title != candidate.title]
        return TopicSelection(
            selected_title=candidate.title,
            selected_reason=reason,
            backup_titles=backups,
            caution_notes=selection.caution_notes,
        )

    def _reference_contexts(self, topic_context: TopicContext, topic_contexts: list[TopicContext]) -> list[TopicContext]:
        ordered = [topic_context]
        ordered.extend(item for item in topic_contexts if item.candidate.title != topic_context.candidate.title)
        return ordered[:5]

    def _assess_originality(
        self,
        contract: object,
        selection: TopicSelection,
        topic_context: TopicContext,
        generated_content,
    ) -> OriginalityAudit:
        try:
            return self.model.assess_originality(
                contract=contract,
                selection=selection,
                topic_context=topic_context,
                generated_content=generated_content,
            )
        except Exception:
            return fallback_originality_audit(topic_context.candidate, generated_content)

    def _truth_brief(self, topic_context: TopicContext) -> str:
        truth_profile = topic_context.truth_profile
        dossier = topic_context.dossier
        lines = [
            "Truth alignment contract:",
            f"- Authority mode: {truth_profile.authority_mode}",
            f"- Source ownership: {truth_profile.source_ownership}",
            f"- Evidence strength: {truth_profile.evidence_strength}",
            f"- Risk level: {truth_profile.risk_level}",
            f"- Conflict level: {truth_profile.conflict_level}",
            f"- Allowed claim posture: {truth_profile.allowed_claim_posture}",
            f"- Provenance rule: {truth_profile.provenance_rule}",
        ]
        if dossier.consensus_summary:
            lines.append(f"- Dossier summary: {dossier.consensus_summary}")
        for note in dossier.disagreement_notes:
            lines.append(f"- Disagreement: {note}")
        for move in truth_profile.required_copy_moves:
            lines.append(f"- Required copy move: {move}")
        for move in truth_profile.forbidden_moves:
            lines.append(f"- Forbidden move: {move}")
        return "\n".join(lines)

    def _truth_feedback(self, topic_context: TopicContext, issues: list[str]) -> str:
        lines = [
            "The draft failed the truth alignment guard.",
            *issues,
            self._truth_brief(topic_context),
            "Rewrite the copy so its certainty, provenance, and tone match the truth profile exactly.",
        ]
        return "\n".join(lines)

    def _deterministic_feedback(self, contract: object, issues: list[str]) -> str | None:
        if not issues:
            return None

        lines = [
            "Fix these deterministic validation issues before anything else.",
            *issues,
        ]

        if "Core idea must contain 3 to 5 bullets." in issues:
            lines.append("Return exactly 3 to 5 `core_idea` bullets. Four is preferred. Never return 6 bullets.")
        if "Post must include at least one mistake, insight, unexpected result, or tradeoff." in issues:
            lines.append("Make at least one `core_idea` bullet and one draft line explicitly mention a mistake, insight, unexpected result, or tradeoff.")
        if contract.day == "Saturday" and "Saturday post must show how thinking evolved." in issues:
            lines.append("For Saturday, explicitly show thinking evolution with phrasing like 'I used to think...', 'I've started...', 'I now assume...', or 'That changed how I...'.")
        if contract.day == "Thursday" and "Thursday post must explain what this actually changes." in issues:
            lines.append("For Thursday, include the literal frame 'What this actually changes is ...' in the core idea or draft.")
        if contract.day == "Thursday" and "Thursday post must include implications." in issues:
            lines.append("For Thursday, include a literal implication line such as 'Implication:' or 'That means ...'.")

        lines.append("Do not defend the current draft. Rewrite the affected sections so every deterministic issue disappears.")
        return "\n".join(lines)

    def _originality_feedback(
        self,
        audit: OriginalityAudit,
        issues: list[str],
    ) -> str:
        lines = [
            "The first draft failed the originality guard.",
            *issues,
            "Do not reuse the source headline framing.",
            "Do not restate the source conclusion directly.",
            f"Required transformation type: {audit.transformation_type}.",
            f"Required new mechanism or insight: {audit.new_mechanism_or_insight}",
            "Rewrite the hook and core claim so the post feels owned rather than aggregated.",
        ]
        return "\n".join(lines)

    def _generate_with_truth_and_originality_guard(
        self,
        contract: object,
        selection: TopicSelection,
        topic_contexts: list[TopicContext],
    ):
        queued_contexts = self._topic_context_queue(selection, topic_contexts)
        rejected_titles: list[str] = []
        last_issues: list[str] = []

        for topic_context in queued_contexts:
            current_selection = self._selection_for_candidate(selection, topic_context, prior_rejections=rejected_titles)
            revision_feedback: str | None = self._truth_brief(topic_context)

            for _ in range(2):
                generated_content = self._generate_with_critic(
                    contract,
                    current_selection,
                    topic_context,
                    self._reference_contexts(topic_context, topic_contexts),
                    revision_feedback=revision_feedback,
                )
                truth_issues = validate_truth_alignment(generated_content, contract, topic_context)
                if truth_issues:
                    last_issues = truth_issues
                    revision_feedback = self._truth_feedback(topic_context, truth_issues)
                    continue

                originality_audit = self._assess_originality(contract, current_selection, topic_context, generated_content)
                originality_issues = validate_originality(generated_content, topic_context.candidate, originality_audit)
                if not originality_issues:
                    generated_content.topic_dossier = topic_context.dossier
                    generated_content.truth_profile = topic_context.truth_profile
                    generated_content.originality_audit = originality_audit
                    generated_content.primary.self_audit.critic_notes.append(
                        f"Authority: {topic_context.truth_profile.authority_mode} / {topic_context.truth_profile.source_ownership}."
                    )
                    generated_content.primary.self_audit.critic_notes.append(
                        f"Originality: {originality_audit.transformation_type} ({originality_audit.originality_score}/10)."
                    )
                    return generated_content, current_selection

                last_issues = originality_issues
                revision_feedback = "\n".join(
                    [
                        self._truth_brief(topic_context),
                        self._originality_feedback(originality_audit, originality_issues),
                    ]
                )

            rejected_titles.append(topic_context.candidate.title)

        raise RuntimeError("No candidate passed the truth/originality guard: " + "; ".join(last_issues))

    def _generate_with_critic(
        self,
        contract: object,
        selection: TopicSelection,
        topic_context: TopicContext,
        reference_contexts: list[TopicContext],
        *,
        revision_feedback: str | None = None,
    ):
        last_issues: list[str] = []
        for _ in range(3):
            generated_content = self.model.generate_content(
                contract=contract,
                selection=selection,
                topic_context=topic_context,
                reference_contexts=reference_contexts,
                creator_context=self.config.creator_context,
                revision_feedback=revision_feedback,
            )
            deterministic_issues = validate_generated_content(generated_content, contract)
            audit = self.model.audit_content(
                contract=contract,
                topic_context=topic_context,
                generated_content=generated_content,
                deterministic_issues=deterministic_issues,
            )
            if not deterministic_issues and audit.passed:
                generated_content.primary.self_audit.critic_notes.extend(audit.reasons)
                return generated_content

            audit_issues = [] if audit.passed else audit.reasons
            last_issues = deterministic_issues + audit_issues
            feedback_parts = [
                revision_feedback,
                self._deterministic_feedback(contract, deterministic_issues),
                *audit_issues,
                audit.revision_instructions,
            ]
            revision_feedback = "\n".join(part for part in feedback_parts if part)

        raise RuntimeError("Content generation failed critic review: " + "; ".join(last_issues))

    def _deliver(self, context: RunContext, generated_content, selected_topic: str, review_url: str | None, send_email: bool) -> DeliveryResult:
        if not send_email:
            return DeliveryResult(status="skipped", detail="Email delivery was skipped by CLI flag.")
        if not self.config.smtp.recipient:
            return DeliveryResult(status="skipped", detail="No recipient configured.")

        summary_stub = type(
            "SummaryStub",
            (),
            {
                "run_id": context.run_id,
                "day": context.day,
                "post_type": context.post_type,
                "selected_topic": selected_topic,
            },
        )
        payload = render_email_payload(summary_stub, generated_content, self.config.smtp.recipient, review_url=review_url)
        return self.email_sender.send(payload)

    def _review_url(self, run_id: str) -> str | None:
        if not self.config.review_base_url:
            return None
        separator = "&" if "?" in self.config.review_base_url else "?"
        return f"{self.config.review_base_url}{separator}run_id={run_id}"


def record_review(storage: StorageBackend, *, run_id: str, decision: str, notes: str) -> ReviewRecord:
    review = ReviewRecord(
        run_id=run_id,
        decision=decision,
        notes=notes,
        decided_at=utc_now().isoformat(),
    )
    storage.record_review(review)
    return review
