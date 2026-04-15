from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pathlib import Path
import shutil
import unittest
from urllib.error import URLError
from uuid import uuid4

from linkedin_content_agent.config import AppConfig, SMTPConfig
from linkedin_content_agent.models import BackupIdea, DeliveryResult, GeneratedContent, ModelAuditResult, OriginalityAudit, PostPackage, RunOptions, SelfAudit, Signal, SourceReference, TopicSelection
from linkedin_content_agent.pipeline import ContentAgent, record_review
from linkedin_content_agent.storage import LocalHybridStorage
from linkedin_content_agent.utils import load_json


def build_generated_content(contract, selection, *, hook: str, mechanism: str) -> GeneratedContent:
    primary = PostPackage(
        day=contract.day,
        post_type=contract.post_type,
        hook=hook,
        core_idea=[
            "What broke first was the workflow boundary between the model output and the tool contract.",
            f"Unexpected result: {mechanism}",
            "Lesson learned: the tradeoff is slower setup for more reliable agent behavior.",
        ],
        draft_post=(
            "I expected the model quality to be the issue.\n"
            "What broke was the workflow boundary between the model output and the tool contract.\n"
            f"Unexpected result: {mechanism}\n"
            "Lesson learned: the tradeoff is slower setup for more reliable agent behavior."
        ),
        visual_suggestion="Screenshot of the failing tool call beside the corrected workflow step.",
        why_this_works="It explains the system mechanism rather than polishing the source claim.",
        source_refs=[SourceReference(source="reddit:MachineLearning", title=selection.selected_title, url="https://example.com/topic")],
        self_audit=SelfAudit(passed_checks=["Mentions what broke, an unexpected result, and a lesson."], critic_notes=[]),
    )
    backups = [
        BackupIdea(
            title="The validation layer matters more than the clever prompt",
            angle="Tradeoff",
            hook="Prompt work did less for me than a simple validation step.",
            why_now="Builders are shipping agents into noisier data paths.",
            visual_suggestion="One failed output versus one validated output.",
        ),
        BackupIdea(
            title="Why agent bugs hide in the handoff, not the model",
            angle="Mistake pattern",
            hook="I blamed the model first. The interface was the real issue.",
            why_now="Teams are spending more time debugging multi-step AI workflows.",
            visual_suggestion="Simple workflow diagram with the failing boundary highlighted.",
        ),
    ]
    return GeneratedContent(primary=primary, backups=backups, selected_topic_reason="Builder-oriented topic with clear evidence.")


class FakeSource:
    def __init__(self, signals):
        self._signals = signals

    def fetch(self):
        return list(self._signals)


class FailingSource:
    def fetch(self):
        raise URLError("temporary source outage")


class PassingModel:
    def choose_topic(self, contract, candidates, topic_override=None):
        selected = topic_override or candidates[0].title
        backups = [candidate.title for candidate in candidates[1:3]]
        return TopicSelection(
            selected_title=selected,
            selected_reason="Chosen for strong evidence.",
            backup_titles=backups,
            caution_notes=[],
        )

    def generate_content(self, *, contract, selection, candidates, creator_context, revision_feedback=None):
        return build_generated_content(
            contract,
            selection,
            hook="Most agent failures look like model problems until you inspect the workflow boundary.",
            mechanism="The deeper mechanism is that protocol checks fail when conversational priors leak into the tool contract.",
        )

    def audit_content(self, *, contract, generated_content, deterministic_issues):
        return ModelAuditResult(passed=not deterministic_issues, reasons=[], revision_instructions="Tighten the builder insight.")

    def assess_originality(self, *, contract, selection, candidate, generated_content):
        return OriginalityAudit(
            source_signal=f"{candidate.supporting_signals[0].source} - {candidate.supporting_signals[0].title}",
            core_claim_from_source=candidate.title,
            transformation_type="deepened",
            new_mechanism_or_insight="The draft explains why protocol adherence breaks at the workflow boundary.",
            originality_score=8.4,
            decision="approve",
        )


class ReframeThenPassModel(PassingModel):
    def __init__(self):
        self.generate_calls: list[str | None] = []

    def generate_content(self, *, contract, selection, candidates, creator_context, revision_feedback=None):
        self.generate_calls.append(revision_feedback)
        if revision_feedback:
            return build_generated_content(
                contract,
                selection,
                hook="The real problem with Opus-style fine-tunes is protocol breakage, not intelligence.",
                mechanism="The deeper mechanism is that chat-optimized tuning degrades tool contract adherence in agent workflows.",
            )
        return build_generated_content(
            contract,
            selection,
            hook=selection.selected_title,
            mechanism="The model feels worse than expected.",
        )

    def assess_originality(self, *, contract, selection, candidate, generated_content):
        if generated_content.primary.hook == selection.selected_title:
            return OriginalityAudit(
                source_signal=f"{candidate.supporting_signals[0].source} - {candidate.supporting_signals[0].title}",
                core_claim_from_source=candidate.title,
                transformation_type="deepened",
                new_mechanism_or_insight="Explain why tool protocol adherence fails instead of repeating the downgrade claim.",
                originality_score=4.2,
                decision="reject",
            )
        return OriginalityAudit(
            source_signal=f"{candidate.supporting_signals[0].source} - {candidate.supporting_signals[0].title}",
            core_claim_from_source=candidate.title,
            transformation_type="deepened",
            new_mechanism_or_insight="The draft reframes the problem around protocol adherence.",
            originality_score=8.3,
            decision="approve",
        )


class FallbackToNextCandidateModel(PassingModel):
    def __init__(self):
        self.attempted_titles: list[str] = []
        self.rejected_title: str | None = None
        self.approved_title: str | None = None

    def choose_topic(self, contract, candidates, topic_override=None):
        selection = super().choose_topic(contract, candidates, topic_override)
        self.rejected_title = selection.selected_title
        remaining = [candidate.title for candidate in candidates if candidate.title != selection.selected_title]
        self.approved_title = remaining[0] if remaining else None
        return selection

    def generate_content(self, *, contract, selection, candidates, creator_context, revision_feedback=None):
        self.attempted_titles.append(selection.selected_title)
        if selection.selected_title == self.rejected_title:
            return build_generated_content(
                contract,
                selection,
                hook=selection.selected_title,
                mechanism="It feels worse in chat than the base model.",
            )
        return build_generated_content(
            contract,
            selection,
            hook="Why chat-first fine-tunes make your agent worse at doing real work",
            mechanism="The deeper mechanism is that chat-first fine-tunes inherit conversational priors that break tool protocol adherence.",
        )

    def assess_originality(self, *, contract, selection, candidate, generated_content):
        if selection.selected_title == self.rejected_title:
            return OriginalityAudit(
                source_signal=f"{candidate.supporting_signals[0].source} - {candidate.supporting_signals[0].title}",
                core_claim_from_source=candidate.title,
                transformation_type="reframed",
                new_mechanism_or_insight="Move away from the downgrade framing and explain the workflow failure mode instead.",
                originality_score=4.0,
                decision="reject",
            )
        return OriginalityAudit(
            source_signal=f"{candidate.supporting_signals[0].source} - {candidate.supporting_signals[0].title}",
            core_claim_from_source=candidate.title,
            transformation_type="applied",
            new_mechanism_or_insight="The draft applies the signal to real workflow reliability instead of repeating the source claim.",
            originality_score=8.1,
            decision="approve",
        )


class NeverOriginalModel(PassingModel):
    def assess_originality(self, *, contract, selection, candidate, generated_content):
        return OriginalityAudit(
            source_signal=f"{candidate.supporting_signals[0].source} - {candidate.supporting_signals[0].title}",
            core_claim_from_source=candidate.title,
            transformation_type="reframed",
            new_mechanism_or_insight="Add a new lens instead of repeating the source.",
            originality_score=3.5,
            decision="reject",
        )

    def generate_content(self, *, contract, selection, candidates, creator_context, revision_feedback=None):
        return build_generated_content(
            contract,
            selection,
            hook=selection.selected_title,
            mechanism="It feels worse in chat than the base model.",
        )


class FakeEmailSender:
    def __init__(self, status="sent", detail="ok"):
        self.status = status
        self.detail = detail
        self.payload = None

    def send(self, payload):
        self.payload = payload
        return DeliveryResult(status=self.status, detail=self.detail)


class PipelineTests(unittest.TestCase):
    def _workspace_run_dir(self) -> Path:
        base = ROOT / "tests" / "_tmp"
        base.mkdir(parents=True, exist_ok=True)
        run_dir = base / uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def _config(self, data_dir: Path) -> AppConfig:
        return AppConfig(
            openai_api_key=None,
            openai_model="gpt-5.1",
            selection_reasoning="low",
            generation_reasoning="medium",
            audit_reasoning="low",
            timezone="Africa/Lagos",
            data_dir=data_dir,
            review_base_url="https://github.com/example/repo/actions/workflows/review_capture.yml",
            signal_limit_per_source=10,
            rss_feeds=(),
            reddit_subreddits=(),
            youtube_channel_ids=(),
            smtp=SMTPConfig(
                host="smtp.example.com",
                port=465,
                username="user",
                password="pass",
                use_ssl=True,
                sender="from@example.com",
                recipient="to@example.com",
            ),
        )

    def _signals(self, titles=None):
        titles = titles or ["Unexpected tradeoff in agent evaluation pipelines"]
        return [
            Signal(
                source="reddit:MachineLearning",
                title=title,
                url=f"https://example.com/{index}",
                published_at="2026-04-15T06:00:00+00:00",
                engagement_hint={"score": 250 - index, "num_comments": 42 - index},
                excerpt="A builder explains why the validation boundary broke their workflow.",
                raw_metadata={},
            )
            for index, title in enumerate(titles, start=1)
        ]

    def test_pipeline_archives_and_records_review(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            sender = FakeEmailSender()
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=PassingModel(),
                email_sender=sender,
                source_adapters=[FakeSource(self._signals())],
            )

            result = agent.run(RunOptions(day_override="Monday", send_email=True))

            self.assertEqual(result.summary.status, "awaiting_review")
            self.assertEqual(result.delivery_result.status, "sent")
            self.assertTrue(result.artifacts.json_path.exists())
            self.assertTrue(result.artifacts.markdown_path.exists())
            self.assertTrue(result.artifacts.prompt_path.exists())
            self.assertIsNotNone(result.generated_content.originality_audit)
            self.assertIsNotNone(sender.payload)

            payload = load_json(result.artifacts.json_path, {})
            self.assertIn("originality_audit", payload["generated_content"])
            self.assertEqual(payload["generated_content"]["originality_audit"]["decision"], "approve")

            review = record_review(storage, run_id=result.summary.run_id, decision="approved", notes="Strong builder angle.")
            self.assertEqual(review.decision, "approved")

            index = load_json(data_dir / "history" / "index.json", {})
            self.assertEqual(index[result.summary.run_id]["status"], "approved")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pipeline_survives_source_warning_and_email_failure(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            sender = FakeEmailSender(status="failed", detail="smtp unavailable")
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=PassingModel(),
                email_sender=sender,
                source_adapters=[FailingSource(), FakeSource(self._signals())],
            )

            result = agent.run(RunOptions(day_override="Monday", send_email=True))

            self.assertEqual(result.delivery_result.status, "failed")
            self.assertTrue(result.warnings)
            self.assertTrue(result.artifacts.json_path.exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pipeline_reframes_once_before_passing_originality_guard(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            model = ReframeThenPassModel()
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=model,
                email_sender=FakeEmailSender(),
                source_adapters=[FakeSource(self._signals(["These Opus fine-tunes are a downgrade"]))],
            )

            result = agent.run(RunOptions(day_override="Monday", send_email=False))

            self.assertEqual(len(model.generate_calls), 2)
            self.assertIsNone(model.generate_calls[0])
            self.assertIsNotNone(model.generate_calls[1])
            self.assertEqual(result.generated_content.originality_audit.decision, "approve")
            self.assertIn("protocol breakage", result.generated_content.primary.hook.lower())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pipeline_falls_back_to_next_candidate_after_originality_rejection(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            model = FallbackToNextCandidateModel()
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=model,
                email_sender=FakeEmailSender(),
                source_adapters=[
                    FakeSource(
                        self._signals(
                            [
                                "These Opus fine-tunes are a downgrade",
                                "Why tool protocol adherence matters more than benchmark wins",
                            ]
                        )
                    )
                ],
            )

            result = agent.run(RunOptions(day_override="Monday", send_email=False))

            self.assertEqual(
                model.attempted_titles,
                [
                    model.rejected_title,
                    model.rejected_title,
                    model.approved_title,
                ],
            )
            self.assertEqual(result.summary.selected_topic, model.approved_title)
            self.assertEqual(result.generated_content.originality_audit.decision, "approve")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pipeline_raises_when_no_candidate_passes_originality_guard(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=NeverOriginalModel(),
                email_sender=FakeEmailSender(),
                source_adapters=[
                    FakeSource(
                        self._signals(
                            [
                                "These Opus fine-tunes are a downgrade",
                                "This eval stack is still a downgrade",
                            ]
                        )
                    )
                ],
            )

            with self.assertRaises(RuntimeError) as context:
                agent.run(RunOptions(day_override="Monday", send_email=False))

            self.assertIn("No candidate passed the originality guard", str(context.exception))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
