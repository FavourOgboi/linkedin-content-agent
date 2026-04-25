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
from linkedin_content_agent.models import (
    BackupIdea,
    DeliveryResult,
    GeneratedContent,
    ModelAuditResult,
    OriginalityAudit,
    PostPackage,
    RunOptions,
    SelfAudit,
    Signal,
    SourceReference,
    TopicSelection,
)
from linkedin_content_agent.pipeline import ContentAgent, record_review
from linkedin_content_agent.storage import LocalHybridStorage
from linkedin_content_agent.utils import load_json


def build_generated_content(
    contract,
    selection,
    *,
    hook: str,
    mechanism: str,
    opening_line: str = "A recent benchmark suggests the model quality is not the main failure point here.",
    include_metrics: bool = False,
    model_name: str | None = None,
) -> GeneratedContent:
    metric_line = "In one setup, refusal rate rose by 42%." if include_metrics else "That claim is still worth testing in your own setup."
    model_line = f"{model_name} was the headline in the discussion." if model_name else "The setup details matter more than the headline."
    core_idea = [
        "What people get wrong is assuming the benchmark headline transfers cleanly into every workflow.",
        f"The deeper mechanism is that {mechanism}",
        "The lesson is to treat the finding as a system-level pattern, not a universal fact.",
    ]
    draft_post = (
        f"{opening_line}\n"
        "Across a few sources, the fragile boundary is the tool contract rather than the top-line model score.\n"
        f"What broke first was the workflow boundary: {mechanism}\n"
        f"Unexpected result: {metric_line}\n"
        f"Lesson learned: {model_line}"
    )
    why_this_works = "It explains the system mechanism and makes the provenance explicit instead of polishing a borrowed claim."

    if contract.day == "Thursday":
        core_idea = [
            "What people get wrong is treating the headline as the change instead of the workflow implication.",
            f"What this actually changes is that {mechanism}",
            "Implication and insight: teams need to evaluate the workflow boundary, not just the model claim.",
        ]
        draft_post = (
            f"{opening_line}\n"
            "Across a few sources, the fragile boundary is the tool contract rather than the top-line model score.\n"
            f"What this actually changes is that {mechanism}\n"
            f"Implication: {metric_line}\n"
            f"That means the setup details matter more than the headline: {model_line}"
        )
        why_this_works = "It interprets the trend and tells the reader what changes in practice."

    primary = PostPackage(
        day=contract.day,
        post_type=contract.post_type,
        hook=hook,
        core_idea=core_idea,
        draft_post=draft_post,
        visual_suggestion="Screenshot of the failing tool call beside the corrected workflow step.",
        why_this_works=why_this_works,
        source_refs=[SourceReference(source="reddit:MachineLearning", title=selection.selected_title, url="https://example.com/topic")],
        self_audit=SelfAudit(
            passed_checks=["Contains provenance, a failure point, and a lesson."],
            critic_notes=[],
        ),
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
            hook="The interface is often the real issue, not the model headline.",
            why_now="Teams are spending more time debugging multi-step AI workflows.",
            visual_suggestion="Simple workflow diagram with the failing boundary highlighted.",
        ),
    ]
    return GeneratedContent(primary=primary, backups=backups, selected_topic_reason="Chosen for strong multi-source relevance.")


class FakeSource:
    def __init__(self, signals):
        self._signals = signals

    def fetch(self):
        return list(self._signals)


class FailingSource:
    def fetch(self):
        raise URLError("temporary source outage")


class PassingModel:
    def choose_topic(self, contract, topic_contexts, topic_override=None):
        selected = topic_override or topic_contexts[0].candidate.title
        backups = [context.candidate.title for context in topic_contexts[1:3]]
        return TopicSelection(
            selected_title=selected,
            selected_reason="Chosen for strong evidence.",
            backup_titles=backups,
            caution_notes=[],
        )

    def generate_content(self, *, contract, selection, topic_context, reference_contexts, creator_context, revision_feedback=None):
        return build_generated_content(
            contract,
            selection,
            hook="Most agent failures look like model problems until you inspect the workflow boundary.",
            mechanism="protocol checks fail when conversational priors leak into the tool contract",
        )

    def audit_content(self, *, contract, topic_context, generated_content, deterministic_issues):
        return ModelAuditResult(passed=not deterministic_issues, reasons=[], revision_instructions="Tighten the systems framing.")

    def assess_originality(self, *, contract, selection, topic_context, generated_content):
        return OriginalityAudit(
            source_signal=f"{topic_context.candidate.supporting_signals[0].source} - {topic_context.candidate.supporting_signals[0].title}",
            core_claim_from_source=topic_context.candidate.title,
            transformation_type="deepened",
            new_mechanism_or_insight="The draft explains why protocol adherence breaks at the workflow boundary.",
            originality_score=8.4,
            decision="approve",
        )


class ReframeThenPassModel(PassingModel):
    def __init__(self):
        self.generate_calls: list[str | None] = []

    def generate_content(self, *, contract, selection, topic_context, reference_contexts, creator_context, revision_feedback=None):
        self.generate_calls.append(revision_feedback)
        if revision_feedback and "originality" in revision_feedback.lower():
            return build_generated_content(
                contract,
                selection,
                hook="The real problem with Opus-style fine-tunes is protocol breakage, not intelligence.",
                mechanism="chat-optimized tuning degrades tool contract adherence in agent workflows",
            )
        return build_generated_content(
            contract,
            selection,
            hook=selection.selected_title,
            mechanism="the model feels worse than expected",
        )

    def assess_originality(self, *, contract, selection, topic_context, generated_content):
        if generated_content.primary.hook == selection.selected_title:
            return OriginalityAudit(
                source_signal=f"{topic_context.candidate.supporting_signals[0].source} - {topic_context.candidate.supporting_signals[0].title}",
                core_claim_from_source=topic_context.candidate.title,
                transformation_type="deepened",
                new_mechanism_or_insight="Explain why tool protocol adherence fails instead of repeating the downgrade claim.",
                originality_score=4.2,
                decision="reject",
            )
        return OriginalityAudit(
            source_signal=f"{topic_context.candidate.supporting_signals[0].source} - {topic_context.candidate.supporting_signals[0].title}",
            core_claim_from_source=topic_context.candidate.title,
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

    def choose_topic(self, contract, topic_contexts, topic_override=None):
        selection = super().choose_topic(contract, topic_contexts, topic_override)
        self.rejected_title = selection.selected_title
        remaining = [context.candidate.title for context in topic_contexts if context.candidate.title != selection.selected_title]
        self.approved_title = remaining[0] if remaining else None
        return selection

    def generate_content(self, *, contract, selection, topic_context, reference_contexts, creator_context, revision_feedback=None):
        self.attempted_titles.append(selection.selected_title)
        if selection.selected_title == self.rejected_title:
            return build_generated_content(
                contract,
                selection,
                hook=selection.selected_title,
                mechanism="it feels worse in chat than the base model",
            )
        return build_generated_content(
            contract,
            selection,
            hook="Why chat-first fine-tunes make your agent worse at doing real work",
            mechanism="chat-first fine-tunes inherit conversational priors that break tool protocol adherence",
        )

    def assess_originality(self, *, contract, selection, topic_context, generated_content):
        if selection.selected_title == self.rejected_title:
            return OriginalityAudit(
                source_signal=f"{topic_context.candidate.supporting_signals[0].source} - {topic_context.candidate.supporting_signals[0].title}",
                core_claim_from_source=topic_context.candidate.title,
                transformation_type="reframed",
                new_mechanism_or_insight="Move away from the downgrade framing and explain the workflow failure mode instead.",
                originality_score=4.0,
                decision="reject",
            )
        return OriginalityAudit(
            source_signal=f"{topic_context.candidate.supporting_signals[0].source} - {topic_context.candidate.supporting_signals[0].title}",
            core_claim_from_source=topic_context.candidate.title,
            transformation_type="applied",
            new_mechanism_or_insight="The draft applies the signal to workflow reliability instead of repeating the source claim.",
            originality_score=8.1,
            decision="approve",
        )


class BuilderThenDowngradeModel(PassingModel):
    def __init__(self):
        self.generate_calls: list[str | None] = []

    def generate_content(self, *, contract, selection, topic_context, reference_contexts, creator_context, revision_feedback=None):
        self.generate_calls.append(revision_feedback)
        if revision_feedback and "truth alignment guard" in revision_feedback.lower():
            return build_generated_content(
                contract,
                selection,
                hook="A recent benchmark makes one thing clear: the workflow boundary matters more than the headline score.",
                mechanism="protocol checks fail when conversational priors leak into the tool contract",
            )
        return build_generated_content(
            contract,
            selection,
            hook="I tested the benchmark claim and the workflow boundary failed first.",
            mechanism="protocol checks fail when conversational priors leak into the tool contract",
            opening_line="I tested the benchmark claim on a live workflow.",
        )


class EchoChamberFallbackModel(PassingModel):
    def __init__(self):
        self.attempted_titles: list[str] = []

    def generate_content(self, *, contract, selection, topic_context, reference_contexts, creator_context, revision_feedback=None):
        self.attempted_titles.append(selection.selected_title)
        if "downgrade" in selection.selected_title.lower():
            return build_generated_content(
                contract,
                selection,
                hook="These fine-tunes are a downgrade for agents.",
                mechanism="discussion threads keep repeating the same downgrade framing",
            )
        return build_generated_content(
            contract,
            selection,
            hook="Protocol adherence is the hidden reason agent eval wins fail in production.",
            mechanism="benchmark gains disappear when tool contracts are looser than the benchmark assumes",
        )


class NeverCredibleModel(PassingModel):
    def assess_originality(self, *, contract, selection, topic_context, generated_content):
        return OriginalityAudit(
            source_signal=f"{topic_context.candidate.supporting_signals[0].source} - {topic_context.candidate.supporting_signals[0].title}",
            core_claim_from_source=topic_context.candidate.title,
            transformation_type="reframed",
            new_mechanism_or_insight="Add a new lens instead of repeating the source.",
            originality_score=3.5,
            decision="reject",
        )

    def generate_content(self, *, contract, selection, topic_context, reference_contexts, creator_context, revision_feedback=None):
        return build_generated_content(
            contract,
            selection,
            hook=selection.selected_title,
            mechanism="it feels worse in chat than the base model",
        )


class SaturdayPositiveReasonModel(PassingModel):
    def __init__(self, test_case: unittest.TestCase):
        self._test_case = test_case
        self.feedback_seen: list[str | None] = []

    def generate_content(self, *, contract, selection, topic_context, reference_contexts, creator_context, revision_feedback=None):
        self.feedback_seen.append(revision_feedback)
        if len(self.feedback_seen) > 1:
            self._test_case.assertNotIn("The Saturday reflection requirement is met", revision_feedback)
            primary = PostPackage(
                day=contract.day,
                post_type=contract.post_type,
                hook="I used to read leaderboards like rankings. I now assume they describe a stack.",
                core_idea=[
                    "I used to read the top model on a chart as the answer.",
                    "I've started treating conflicting evals as a sign that my thinking evolved around the whole stack.",
                    "The insight is that setup details matter more than a single benchmark headline.",
                ],
                draft_post=(
                    "I used to read the leaderboard and pick the top model.\n"
                    "A recent benchmark and a few external writeups changed how I read the stack.\n"
                    "Across a few sources, I’ve started treating evals as properties of a stack instead.\n"
                    "I now assume the runtime, quantization, prompts, and agent design matter as much as the benchmark itself.\n"
                    "That changed how I choose what to test next."
                ),
                visual_suggestion="Simple stack diagram from hardware through prompts and tool calls.",
                why_this_works="It shows how the thinking changed without pretending the benchmarks were mine.",
                source_refs=[SourceReference(source="reddit:LocalLLaMA", title=selection.selected_title, url="https://example.com/topic")],
                self_audit=SelfAudit(passed_checks=["Shows how thinking evolved and keeps provenance explicit."], critic_notes=[]),
            )
            backups = [
                BackupIdea(
                    title="Why conflicting evals improved my model selection process",
                    angle="Reflection",
                    hook="The disagreement between benchmarks changed my workflow.",
                    why_now="People still read leaderboards as global rankings.",
                    visual_suggestion="Two conflicting benchmark screenshots and one systems diagram.",
                ),
                BackupIdea(
                    title="Leaderboards are properties of a stack, not just a model",
                    angle="Insight",
                    hook="I no longer read eval wins as standalone truths.",
                    why_now="Agent stacks keep widening the gap between leaderboard wins and production behavior.",
                    visual_suggestion="Layered stack sketch.",
                ),
            ]
            return GeneratedContent(primary=primary, backups=backups, selected_topic_reason="Saturday reflection.")

        primary = PostPackage(
            day=contract.day,
            post_type=contract.post_type,
            hook="Why benchmark disagreement matters for agent stacks.",
            core_idea=[
                "Conflicting benchmarks exposed a gap in model ranking interpretation.",
                "The insight is that stack context matters more than I expected.",
            ],
            draft_post=(
                "Across a few community benchmarks, the same model looked different across stacks.\n"
                "The insight is that stack context matters more than I expected.\n"
                "The tradeoff is slower interpretation for better decisions."
            ),
            visual_suggestion="Benchmark snippets beside a stack diagram.",
            why_this_works="It is technically grounded, but it still reads like commentary rather than reflection.",
            source_refs=[SourceReference(source="reddit:LocalLLaMA", title=selection.selected_title, url="https://example.com/topic")],
            self_audit=SelfAudit(passed_checks=["Explicit provenance is present."], critic_notes=[]),
        )
        backups = [
            BackupIdea(
                title="Why conflicting evals matter",
                angle="Reflection",
                hook="Benchmark disagreement changed how I read rankings.",
                why_now="More builders are discovering stack-dependent behavior.",
                visual_suggestion="Two benchmark screenshots.",
            ),
            BackupIdea(
                title="Stack context beats headline ranking",
                angle="Insight",
                hook="The stack changes the meaning of the score.",
                why_now="Agent workflows make eval interpretation harder.",
                visual_suggestion="Stack diagram.",
            ),
        ]
        return GeneratedContent(primary=primary, backups=backups, selected_topic_reason="Saturday reflection.")

    def audit_content(self, *, contract, topic_context, generated_content, deterministic_issues):
        return ModelAuditResult(
            passed=True,
            reasons=[
                "The Saturday reflection requirement is met: the post clearly shows evolution in thinking.",
                "Provenance and claim posture are correct.",
            ],
            revision_instructions="Strengthen the explicit how-thinking-evolved language.",
        )


class DeterministicRetryModel(PassingModel):
    def __init__(self, test_case: unittest.TestCase):
        self._test_case = test_case
        self.generate_calls: list[str | None] = []

    def generate_content(self, *, contract, selection, topic_context, reference_contexts, creator_context, revision_feedback=None):
        self.generate_calls.append(revision_feedback)
        if len(self.generate_calls) > 1:
            self._test_case.assertIn("Return exactly 3 to 5 `core_idea` bullets", revision_feedback)
            return build_generated_content(
                contract,
                selection,
                hook="I used to read leaderboards like rankings. I now assume they describe a stack.",
                mechanism="stack context changes what the same benchmark score really means",
                opening_line="A recent benchmark and a few external writeups changed how I read model rankings.",
            )

        primary = PostPackage(
            day=contract.day,
            post_type=contract.post_type,
            hook="Why benchmark disagreement matters for agent stacks.",
            core_idea=[
                "Benchmark disagreement matters.",
                "The stack matters.",
                "The runtime matters.",
                "The prompt matters.",
                "The eval harness matters.",
                "The deployment target matters.",
            ],
            draft_post=(
                "Across a few sources, the same model looked different across stacks.\n"
                "The stack context matters more than the benchmark headline.\n"
                "That tradeoff is slower interpretation for better decisions."
            ),
            visual_suggestion="Benchmark snippets beside a stack diagram.",
            why_this_works="It is technically grounded, but it still needs explicit Saturday reflection language.",
            source_refs=[SourceReference(source="reddit:LocalLLaMA", title=selection.selected_title, url="https://example.com/topic")],
            self_audit=SelfAudit(passed_checks=["Explicit provenance is present."], critic_notes=[]),
        )
        backups = [
            BackupIdea(
                title="Why benchmark disagreement matters",
                angle="Reflection",
                hook="Benchmark disagreement changed how I read rankings.",
                why_now="More builders are discovering stack-dependent behavior.",
                visual_suggestion="Two benchmark screenshots.",
            ),
            BackupIdea(
                title="Stack context beats headline ranking",
                angle="Insight",
                hook="The stack changes the meaning of the score.",
                why_now="Agent workflows make eval interpretation harder.",
                visual_suggestion="Stack diagram.",
            ),
        ]
        return GeneratedContent(primary=primary, backups=backups, selected_topic_reason="Saturday reflection.")

    def audit_content(self, *, contract, topic_context, generated_content, deterministic_issues):
        return ModelAuditResult(
            passed=True,
            reasons=["The provenance is otherwise sound."],
            revision_instructions="Fix the deterministic structure and reflection requirements first.",
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
            run_notes_dir=data_dir / "run_notes",
        )

    def _signal(
        self,
        *,
        title: str,
        source: str = "reddit:MachineLearning",
        url: str,
        excerpt: str = "A builder explains why the validation boundary broke the workflow.",
    ) -> Signal:
        return Signal(
            source=source,
            title=title,
            url=url,
            published_at="2026-04-15T06:00:00+00:00",
            engagement_hint={"score": 250, "num_comments": 42},
            excerpt=excerpt,
            raw_metadata={},
        )

    def test_pipeline_archives_truth_profile_and_records_review(self) -> None:
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
                source_adapters=[
                    FakeSource(
                        [
                            self._signal(title="Unexpected tradeoff in agent evaluation pipelines", url="https://example.com/1"),
                            self._signal(
                                title="Why agent evaluation pipelines break at the workflow boundary",
                                source="rss:blog",
                                url="https://github.com/example/agent-eval",
                                excerpt="A technical writeup explains why protocol adherence fails at the tool boundary.",
                            ),
                        ]
                    )
                ],
            )

            result = agent.run(RunOptions(day_override="Monday", send_email=True))

            self.assertEqual(result.summary.status, "awaiting_review")
            self.assertEqual(result.delivery_result.status, "sent")
            self.assertTrue(result.artifacts.json_path.exists())
            self.assertTrue(result.artifacts.markdown_path.exists())
            self.assertTrue(result.artifacts.prompt_path.exists())
            self.assertTrue(result.summary.creator_post_type)
            self.assertTrue(result.summary.topic_pillar)
            self.assertIsNotNone(result.generated_content.originality_audit)
            self.assertIsNotNone(result.generated_content.truth_profile)
            self.assertIsNotNone(result.generated_content.topic_dossier)
            self.assertEqual(result.generated_content.truth_profile.authority_mode, "applied_analyst")
            self.assertIsNotNone(sender.payload)

            payload = load_json(result.artifacts.json_path, {})
            self.assertIn("truth_profile", payload["generated_content"])
            self.assertIn("topic_dossier", payload["generated_content"])
            self.assertEqual(payload["generated_content"]["originality_audit"]["decision"], "approve")
            self.assertEqual(payload["summary"]["creator_post_type"], result.summary.creator_post_type)
            self.assertEqual(payload["summary"]["topic_pillar"], result.summary.topic_pillar)

            review = record_review(storage, run_id=result.summary.run_id, decision="approved", notes="Strong analyst angle.")
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
                source_adapters=[
                    FailingSource(),
                    FakeSource(
                        [
                            self._signal(title="Unexpected tradeoff in agent evaluation pipelines", url="https://example.com/1"),
                            self._signal(
                                title="Why protocol adherence matters in agent evaluation pipelines",
                                source="rss:blog",
                                url="https://github.com/example/agent-eval",
                                excerpt="A technical writeup explains why protocol adherence fails at the tool boundary.",
                            ),
                        ]
                    ),
                ],
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
                source_adapters=[
                    FakeSource(
                        [
                            self._signal(title="These Opus fine-tunes are a downgrade", url="https://example.com/1"),
                            self._signal(
                                title="Why tool protocol adherence matters more than benchmark wins",
                                source="rss:blog",
                                url="https://github.com/example/opus-agent-eval",
                                excerpt="A repo-backed evaluation shows tool contract failures are often the real boundary.",
                            ),
                        ]
                    )
                ],
            )

            result = agent.run(RunOptions(day_override="Monday", send_email=False))

            self.assertEqual(len(model.generate_calls), 2)
            self.assertIn("originality", (model.generate_calls[1] or "").lower())
            self.assertEqual(result.generated_content.originality_audit.decision, "approve")
            self.assertIn("protocol breakage", result.generated_content.primary.hook.lower())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pipeline_post_type_override_wins(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=PassingModel(),
                email_sender=FakeEmailSender(),
                source_adapters=[
                    FakeSource(
                        [
                            self._signal(title="Unexpected tradeoff in agent evaluation pipelines", url="https://example.com/1"),
                            self._signal(
                                title="Why protocol adherence matters in agent evaluation pipelines",
                                source="rss:blog",
                                url="https://github.com/example/agent-eval",
                                excerpt="A technical writeup explains why protocol adherence fails at the tool boundary.",
                            ),
                        ]
                    )
                ],
            )

            result = agent.run(RunOptions(day_override="Tuesday", post_type_override="teaching", send_email=False))

            self.assertEqual(result.summary.creator_post_type, "teaching")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pipeline_does_not_treat_positive_audit_notes_as_failures(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            model = SaturdayPositiveReasonModel(self)
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=model,
                email_sender=FakeEmailSender(),
                source_adapters=[
                    FakeSource(
                        [
                            self._signal(title="A benchmark changed how I read model rankings", url="https://example.com/1"),
                            self._signal(
                                title="Why one benchmark headline should change how you read agent stacks",
                                source="rss:blog",
                                url="https://simonwillison.net/example",
                                excerpt="A technical writeup explains how stack context changes what an eval result means.",
                            ),
                        ]
                    )
                ],
            )

            result = agent.run(RunOptions(day_override="Saturday", send_email=False))

            self.assertEqual(len(model.feedback_seen), 2)
            self.assertIn("started treating", result.generated_content.primary.draft_post.lower())
            self.assertEqual(result.generated_content.truth_profile.authority_mode, "applied_analyst")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pipeline_recovers_from_deterministic_structure_and_saturday_feedback(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            model = DeterministicRetryModel(self)
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=model,
                email_sender=FakeEmailSender(),
                source_adapters=[
                    FakeSource(
                        [
                            self._signal(title="A benchmark changed how I read model rankings", url="https://example.com/1"),
                            self._signal(
                                title="Why one benchmark headline should change how you read agent stacks",
                                source="rss:blog",
                                url="https://simonwillison.net/example",
                                excerpt="A technical writeup explains how stack context changes what an eval result means.",
                            ),
                        ]
                    )
                ],
            )

            result = agent.run(RunOptions(day_override="Saturday", send_email=False))

            self.assertEqual(len(model.generate_calls), 2)
            self.assertLessEqual(len(result.generated_content.primary.core_idea), 5)
            self.assertIn("i now assume", result.generated_content.primary.hook.lower())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pipeline_downgrades_builder_language_to_applied_analyst(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            model = BuilderThenDowngradeModel()
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=model,
                email_sender=FakeEmailSender(),
                source_adapters=[
                    FakeSource(
                        [
                            self._signal(title="Unexpected tradeoff in agent evaluation pipelines", url="https://example.com/1"),
                            self._signal(
                                title="Why protocol adherence matters in agent evaluation pipelines",
                                source="rss:blog",
                                url="https://github.com/example/agent-eval",
                                excerpt="A technical writeup explains why protocol adherence fails at the tool boundary.",
                            ),
                        ]
                    )
                ],
            )

            result = agent.run(RunOptions(day_override="Monday", send_email=False))

            self.assertEqual(len(model.generate_calls), 2)
            self.assertEqual(result.generated_content.truth_profile.authority_mode, "applied_analyst")
            self.assertNotIn("i tested", result.generated_content.primary.draft_post.lower())
            self.assertIn("recent benchmark", result.generated_content.primary.draft_post.lower())
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
                        [
                            self._signal(title="These Opus fine-tunes are a downgrade", url="https://example.com/1"),
                            self._signal(
                                title="Why tool protocol adherence matters more than benchmark wins",
                                source="rss:blog",
                                url="https://github.com/example/agent-eval",
                                excerpt="A repo-backed evaluation explains the workflow failure mode.",
                            ),
                            self._signal(
                                title="Tool protocol adherence is the real eval boundary",
                                source="rss:blog",
                                url="https://openai.com/research/agent-evals",
                                excerpt="A research-style writeup focuses on contract adherence instead of chat quality.",
                            ),
                        ]
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

    def test_pipeline_rejects_echo_chamber_topic_and_falls_back(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            model = EchoChamberFallbackModel()
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=model,
                email_sender=FakeEmailSender(),
                source_adapters=[
                    FakeSource(
                        [
                            self._signal(title="These Opus fine-tunes are a downgrade", url="https://example.com/1"),
                            self._signal(title="Why these Opus fine-tunes are still a downgrade", source="reddit:LocalLLaMA", url="https://example.com/2"),
                            self._signal(title="Opus fine-tunes feel like a downgrade in agents", source="hackernews", url="https://example.com/3"),
                            self._signal(
                                title="Protocol adherence is the hidden eval boundary in agents",
                                source="rss:blog",
                                url="https://github.com/example/protocol-evals",
                                excerpt="A repo-backed evaluation points to contract adherence rather than generic downgrade claims.",
                            ),
                        ]
                    )
                ],
            )

            result = agent.run(RunOptions(day_override="Thursday", send_email=False))

            self.assertGreaterEqual(len(model.attempted_titles), 3)
            self.assertEqual(result.summary.selected_topic, "Protocol adherence is the hidden eval boundary in agents")
            self.assertFalse(result.generated_content.topic_dossier.weak_signal_echo)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_pipeline_raises_when_no_candidate_passes_truth_or_originality_guard(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            data_dir = temp_dir / "data"
            config = self._config(data_dir)
            storage = LocalHybridStorage(data_dir)
            agent = ContentAgent(
                config=config,
                storage=storage,
                model=NeverCredibleModel(),
                email_sender=FakeEmailSender(),
                source_adapters=[
                    FakeSource(
                        [
                            self._signal(title="These Opus fine-tunes are a downgrade", url="https://example.com/1"),
                            self._signal(title="This eval stack is still a downgrade", source="reddit:LocalLLaMA", url="https://example.com/2"),
                        ]
                    )
                ],
            )

            with self.assertRaises(RuntimeError) as context:
                agent.run(RunOptions(day_override="Monday", send_email=False))

            self.assertIn("No candidate passed the truth/originality guard", str(context.exception))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
