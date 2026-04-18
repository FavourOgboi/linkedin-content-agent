from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import unittest

from linkedin_content_agent.day_contracts import resolve_day_contract
from linkedin_content_agent.models import (
    BackupIdea,
    DossierSource,
    GeneratedContent,
    OriginalityAudit,
    PostPackage,
    ScoreBreakdown,
    SelfAudit,
    SourceReference,
    TopicCandidate,
    TopicContext,
    TopicDossier,
    TruthProfile,
)
from linkedin_content_agent.validation import validate_generated_content, validate_originality, validate_truth_alignment


class ValidationTests(unittest.TestCase):
    def _valid_monday_content(self) -> GeneratedContent:
        primary = PostPackage(
            day="Monday",
            post_type="Build / Experiment",
            hook="A recent benchmark suggests the workflow boundary matters more than the model headline.",
            core_idea=[
                "What people get wrong is assuming the benchmark headline transfers cleanly into every workflow.",
                "The deeper mechanism is conversational bias leaking into tool contract adherence.",
                "The lesson: treat cleanup as a pipeline tradeoff, not a universal model verdict.",
            ],
            draft_post=(
                "A recent benchmark suggests the workflow boundary matters more than the model headline.\n"
                "Across a few sources, the fragile boundary is the tool contract rather than the top-line score.\n"
                "What broke first was schema drift at the tool boundary.\n"
                "Unexpected result: setup details mattered more than the benchmark headline.\n"
                "Lesson learned: the real tradeoff is control versus speed."
            ),
            visual_suggestion="Before/after screenshot of the dataset plus one failed row example.",
            why_this_works="It anchors the post in a concrete workflow mistake while making the provenance explicit.",
            source_refs=[SourceReference(source="reddit:MachineLearning", title="Test source", url="https://example.com")],
            self_audit=SelfAudit(passed_checks=["Contains provenance, a failure point, and a lesson."], critic_notes=[]),
        )
        backups = [
            BackupIdea(
                title="Why schema drift kills LLM cleaning runs",
                angle="Failure pattern",
                hook="The first thing that broke was not the model. It was the schema assumption.",
                why_now="More builders are pushing LLMs into messy operational data.",
                visual_suggestion="Schema diff screenshot.",
            ),
            BackupIdea(
                title="Prompt length is the wrong optimization target",
                angle="Tradeoff",
                hook="The better result came from context design, not a longer prompt.",
                why_now="People still over-index on prompt verbosity.",
                visual_suggestion="Prompt A vs Prompt B comparison.",
            ),
        ]
        return GeneratedContent(primary=primary, backups=backups, selected_topic_reason="Strong analyst signal.")

    def _source_candidate(self, title: str = "These Opus fine-tunes are a downgrade") -> TopicCandidate:
        return TopicCandidate(
            title=title,
            score_total=1.0,
            score_breakdown=ScoreBreakdown(
                source_weight=1.0,
                recency=1.0,
                relevance=1.0,
                evidence_strength=1.0,
                novelty_penalty=0.0,
                total=4.0,
            ),
            day_fit="strong",
            evidence=["Source headline about fine-tunes being a downgrade."],
            angles=["insight"],
            novelty_penalty=0.0,
            supporting_signals=[SourceReference(source="reddit:LocalLLaMA", title=title, url="https://example.com/source")],
        )

    def _topic_context(
        self,
        *,
        authority_mode: str = "applied_analyst",
        source_ownership: str = "second_hand",
        evidence_strength: str = "medium",
        risk_level: str = "medium",
        conflict_level: str = "low",
        weak_signal_echo: bool = False,
        source_count: int = 2,
        stronger_source_present: bool = True,
    ) -> TopicContext:
        candidate = self._source_candidate()
        dossier_sources = [
            DossierSource(
                reference=SourceReference(source="reddit:LocalLLaMA", title=candidate.title, url="https://example.com/source"),
                source_quality="discussion",
                evidence_type="discussion",
                claim=candidate.title,
                confidence="weak",
            )
        ]
        if stronger_source_present:
            dossier_sources.append(
                DossierSource(
                    reference=SourceReference(
                        source="rss:blog",
                        title="Protocol adherence is the hidden eval boundary",
                        url="https://github.com/example/protocol-eval",
                    ),
                    source_quality="reproducible",
                    evidence_type="repo",
                    claim="A repo-backed evaluation points to protocol adherence instead of a simple downgrade claim.",
                    confidence="strong",
                )
            )

        dossier = TopicDossier(
            topic_title=candidate.title,
            primary_signal=candidate.supporting_signals[0],
            sources=dossier_sources[:source_count],
            source_count=source_count,
            claim_summaries=[source.claim for source in dossier_sources[:source_count]],
            consensus_summary="The stable angle is the workflow mechanism rather than the headline claim.",
            disagreement_notes=["The sources do not fully agree on the mechanism."] if conflict_level == "high" else [],
            stronger_source_present=stronger_source_present,
            weak_signal_echo=weak_signal_echo,
        )
        truth_profile = TruthProfile(
            source_ownership=source_ownership,
            evidence_strength=evidence_strength,
            risk_level=risk_level,
            authority_mode=authority_mode,
            position="refine",
            conflict_level=conflict_level,
            provenance_rule="Attribute the claim to external sources in the opening lines.",
            allowed_claim_posture="Be bold and technical, but interpret the evidence rather than impersonating the original experiment.",
            required_copy_moves=["State provenance in the hook or first two lines."],
            forbidden_moves=["Do not present external experiments as your own."],
            allows_first_person_experiment=source_ownership in {"first_hand", "mixed"},
            requires_explicit_provenance=source_ownership in {"second_hand", "mixed"} or authority_mode in {"amplifier", "exploratory"},
            allows_exact_metrics=source_ownership in {"first_hand", "mixed"} or stronger_source_present,
        )
        return TopicContext(candidate=candidate, dossier=dossier, truth_profile=truth_profile)

    def test_valid_monday_content_passes(self) -> None:
        content = self._valid_monday_content()
        issues = validate_generated_content(content, resolve_day_contract("Monday"))
        self.assertEqual(issues, [])

    def test_invalid_content_is_rejected(self) -> None:
        content = self._valid_monday_content()
        content.primary.hook = "This game changer will launch faster for everyone"
        content.primary.draft_post = "This is basically what an LLM is. It is amazing."
        issues = validate_generated_content(content, resolve_day_contract("Monday"))
        self.assertTrue(any("hype" in issue.lower() for issue in issues))
        self.assertTrue(any("basic explanatory" in issue.lower() for issue in issues))

    def test_originality_rejects_source_framing_reuse(self) -> None:
        content = self._valid_monday_content()
        content.primary.hook = "These Opus fine-tunes are a downgrade"
        content.primary.core_idea = [
            "These Opus fine-tunes are a downgrade in tool use.",
            "They feel worse than the base model.",
            "That is the whole lesson.",
        ]
        audit = OriginalityAudit(
            source_signal="reddit:LocalLLaMA - These Opus fine-tunes are a downgrade",
            core_claim_from_source="These Opus fine-tunes are a downgrade",
            transformation_type="reframed",
            new_mechanism_or_insight="Add a system-level explanation for why tool use breaks.",
            originality_score=4.2,
            decision="reject",
        )
        issues = validate_originality(content, self._source_candidate(), audit)
        self.assertTrue(any("too similar" in issue.lower() for issue in issues))
        self.assertTrue(any("below 7" in issue.lower() for issue in issues))

    def test_originality_passes_transformed_single_source_draft(self) -> None:
        content = self._valid_monday_content()
        content.primary.hook = "The real problem with Opus-style fine-tunes is protocol breakage, not intelligence."
        content.primary.core_idea = [
            "The failure showed up at the tool boundary, not the reasoning benchmark.",
            "The deeper mechanism is conversational bias leaking into tool contract adherence.",
            "That tradeoff matters more than benchmark wins in agents.",
        ]
        audit = OriginalityAudit(
            source_signal="reddit:LocalLLaMA - These Opus fine-tunes are a downgrade",
            core_claim_from_source="These Opus fine-tunes are a downgrade",
            transformation_type="deepened",
            new_mechanism_or_insight="Tool protocol adherence degrades because the fine-tune inherits chat-first priors.",
            originality_score=8.4,
            decision="approve",
        )
        issues = validate_originality(content, self._source_candidate(), audit)
        self.assertEqual(issues, [])

    def test_truth_rejects_first_hand_language_on_second_hand_post(self) -> None:
        content = self._valid_monday_content()
        content.primary.draft_post = (
            "I tested the benchmark claim myself.\n"
            "What broke for me was the tool contract.\n"
            "Unexpected result: the refusal rate jumped.\n"
            "Lesson learned: the benchmark was right."
        )
        issues = validate_truth_alignment(content, resolve_day_contract("Monday"), self._topic_context())
        self.assertTrue(any("first-person experiment language" in issue.lower() for issue in issues))

    def test_truth_passes_applied_analyst_with_explicit_provenance(self) -> None:
        content = self._valid_monday_content()
        issues = validate_truth_alignment(content, resolve_day_contract("Monday"), self._topic_context())
        self.assertEqual(issues, [])

    def test_truth_rejects_unsupported_metrics(self) -> None:
        content = self._valid_monday_content()
        content.primary.draft_post += "\nThe refusal rate rose by 42%."
        topic_context = self._topic_context(stronger_source_present=False, evidence_strength="weak", risk_level="high")
        topic_context.truth_profile.allows_exact_metrics = False
        issues = validate_truth_alignment(content, resolve_day_contract("Monday"), topic_context)
        self.assertTrue(any("exact metrics" in issue.lower() for issue in issues))

    def test_truth_rejects_unknown_model_version(self) -> None:
        content = self._valid_monday_content()
        content.primary.draft_post += "\nClaude-4.6 Opus was the model in question."
        issues = validate_truth_alignment(content, resolve_day_contract("Monday"), self._topic_context())
        self.assertTrue(any("model names or versions" in issue.lower() for issue in issues))

    def test_truth_rejects_echo_chamber_without_stronger_source(self) -> None:
        content = self._valid_monday_content()
        topic_context = self._topic_context(
            authority_mode="exploratory",
            evidence_strength="weak",
            risk_level="high",
            conflict_level="high",
            weak_signal_echo=True,
            source_count=3,
            stronger_source_present=False,
        )
        issues = validate_truth_alignment(content, resolve_day_contract("Monday"), topic_context)
        self.assertTrue(any("echoing low-quality sources" in issue.lower() for issue in issues))

    def test_saturday_accepts_natural_thinking_evolved_phrasing(self) -> None:
        content = self._valid_monday_content()
        content.primary.day = "Saturday"
        content.primary.post_type = "Thinking / Reflection"
        content.primary.hook = "I used to read leaderboards like rankings. I now assume they describe a stack."
        content.primary.core_idea = [
            "I used to read the top model on a chart as the answer.",
            "I've started treating conflicting evals as a sign that my thinking evolved around the whole stack.",
            "The insight is that setup details matter more than a single benchmark headline.",
        ]
        content.primary.draft_post = (
            "I used to read the leaderboard and pick the top model.\n"
            "I've started treating evals as properties of a stack instead.\n"
            "I now assume the runtime, quantization, prompts, and agent design matter as much as the benchmark itself.\n"
            "That changed how I choose what to test next."
        )

        issues = validate_generated_content(content, resolve_day_contract("Saturday"))
        self.assertFalse(any("thinking evolved" in issue.lower() for issue in issues))


if __name__ == "__main__":
    unittest.main()
