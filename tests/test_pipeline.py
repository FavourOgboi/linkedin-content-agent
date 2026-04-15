from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dataclasses import asdict
from pathlib import Path
import shutil
import unittest
from urllib.error import URLError
from uuid import uuid4

from linkedin_content_agent.config import AppConfig, SMTPConfig
from linkedin_content_agent.emailer import SMTPEmailSender
from linkedin_content_agent.models import BackupIdea, DeliveryResult, GeneratedContent, ModelAuditResult, PostPackage, RunOptions, SelfAudit, Signal, SourceReference, TopicSelection
from linkedin_content_agent.pipeline import ContentAgent, record_review
from linkedin_content_agent.storage import LocalHybridStorage
from linkedin_content_agent.utils import load_json


class FakeSource:
    def __init__(self, signals):
        self._signals = signals

    def fetch(self):
        return list(self._signals)


class FailingSource:
    def fetch(self):
        raise URLError("temporary source outage")


class FakeModel:
    def choose_topic(self, contract, candidates, topic_override=None):
        selected = topic_override or candidates[0].title
        backups = [candidate.title for candidate in candidates[1:3]]
        return TopicSelection(selected_title=selected, selected_reason="Chosen for strong evidence.", backup_titles=backups, caution_notes=[])

    def generate_content(self, *, contract, selection, candidates, creator_context, revision_feedback=None):
        primary = PostPackage(
            day=contract.day,
            post_type=contract.post_type,
            hook="Most agent failures look like model problems until you inspect the workflow boundary.",
            core_idea=[
                "A messy handoff between extraction and validation created the first mistake.",
                "The unexpected result was that one schema check saved more time than prompt tuning.",
                "The tradeoff was slower setup for cleaner downstream behavior.",
            ],
            draft_post=(
                "I expected the LLM to be the weak link.\n"
                "The real mistake was the workflow boundary between extraction and validation.\n"
                "Unexpected result: one schema check saved more time than prompt tuning.\n"
                "That tradeoff is slower setup for a more reliable agent pipeline."
            ),
            visual_suggestion="Screenshot of the failing step beside the corrected schema check.",
            why_this_works="It sounds like a builder sharing a workflow mistake and the system insight behind it.",
            source_refs=[SourceReference(source="reddit:MachineLearning", title=selection.selected_title, url="https://example.com/topic")],
            self_audit=SelfAudit(passed_checks=["Mentions a mistake, an unexpected result, and a tradeoff."], critic_notes=[]),
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

    def audit_content(self, *, contract, generated_content, deterministic_issues):
        return ModelAuditResult(passed=not deterministic_issues, reasons=[], revision_instructions="Tighten the builder insight.")


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

    def _signals(self):
        return [
            Signal(
                source="reddit:MachineLearning",
                title="Unexpected tradeoff in agent evaluation pipelines",
                url="https://example.com/topic",
                published_at="2026-04-15T06:00:00+00:00",
                engagement_hint={"score": 250, "num_comments": 42},
                excerpt="A builder explains why the validation boundary broke their workflow.",
                raw_metadata={},
            )
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
                model=FakeModel(),
                email_sender=sender,
                source_adapters=[FakeSource(self._signals())],
            )

            result = agent.run(RunOptions(day_override="Monday", send_email=True))

            self.assertEqual(result.summary.status, "awaiting_review")
            self.assertEqual(result.delivery_result.status, "sent")
            self.assertTrue(result.artifacts.json_path.exists())
            self.assertTrue(result.artifacts.markdown_path.exists())
            self.assertTrue(result.artifacts.prompt_path.exists())
            self.assertIsNotNone(sender.payload)

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
                model=FakeModel(),
                email_sender=sender,
                source_adapters=[FailingSource(), FakeSource(self._signals())],
            )

            result = agent.run(RunOptions(day_override="Monday", send_email=True))

            self.assertEqual(result.delivery_result.status, "failed")
            self.assertTrue(result.warnings)
            self.assertTrue(result.artifacts.json_path.exists())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
