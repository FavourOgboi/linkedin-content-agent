from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from linkedin_content_agent.config import AppConfig
from linkedin_content_agent.day_contracts import resolve_day_contract, resolve_topic_choice
from linkedin_content_agent.emailer import SMTPEmailSender
from linkedin_content_agent.models import DeliveryResult, ReviewRecord, RunOptions, TopicCandidate, TopicSelection
from linkedin_content_agent.models import AgentRunResult, RunContext
from linkedin_content_agent.openai_client import ContentModel, OpenAIContentModel
from linkedin_content_agent.rendering import render_email_payload
from linkedin_content_agent.scoring import rank_signals
from linkedin_content_agent.sources.base import safe_fetch
from linkedin_content_agent.sources.catalog import build_default_sources
from linkedin_content_agent.storage import LocalHybridStorage, StorageBackend
from linkedin_content_agent.utils import slugify, utc_now
from linkedin_content_agent.validation import validate_generated_content


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

        selection = self.model.choose_topic(contract, candidates, options.topic_override)
        selected_topic = resolve_topic_choice(options.topic_override, selection.selected_title)
        effective_selection = TopicSelection(
            selected_title=selected_topic,
            selected_reason=selection.selected_reason,
            backup_titles=selection.backup_titles,
            caution_notes=selection.caution_notes,
        )
        if options.topic_override and all(candidate.title != selected_topic for candidate in candidates):
            candidates = [self._manual_candidate(selected_topic, signals)] + candidates

        prompt_payload = {
            "run_id": context.run_id,
            "contract": asdict(contract),
            "selection": asdict(effective_selection),
            "candidates": [asdict(candidate) for candidate in candidates[:5]],
            "signal_count": len(signals),
        }

        generated_content = self._generate_with_critic(contract, effective_selection, candidates)
        review_url = self._review_url(context.run_id)
        delivery_result = self._deliver(context, generated_content, selected_topic, review_url, options.send_email)
        summary, artifacts = self.storage.save_run(
            context=context,
            selected_topic=selected_topic,
            generated_content=generated_content,
            candidates=candidates,
            signals=signals,
            delivery_result=delivery_result,
            warnings=warnings,
            prompt_payload=prompt_payload,
            review_url=review_url,
        )
        return AgentRunResult(
            summary=summary,
            generated_content=generated_content,
            candidates=candidates,
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

    def _generate_with_critic(self, contract: object, selection: TopicSelection, candidates: list[TopicCandidate]):
        revision_feedback: str | None = None
        last_issues: list[str] = []
        for _ in range(3):
            generated_content = self.model.generate_content(
                contract=contract,
                selection=selection,
                candidates=candidates,
                creator_context=self.config.creator_context,
                revision_feedback=revision_feedback,
            )
            deterministic_issues = validate_generated_content(generated_content, contract)
            audit = self.model.audit_content(
                contract=contract,
                generated_content=generated_content,
                deterministic_issues=deterministic_issues,
            )
            if not deterministic_issues and audit.passed:
                generated_content.primary.self_audit.critic_notes.extend(audit.reasons)
                return generated_content

            last_issues = deterministic_issues + audit.reasons
            revision_feedback = "\n".join(last_issues + [audit.revision_instructions])

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
