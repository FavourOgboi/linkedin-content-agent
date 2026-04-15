from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import unittest

from linkedin_content_agent.day_contracts import resolve_day_contract
from linkedin_content_agent.models import BackupIdea, GeneratedContent, OriginalityAudit, PostPackage, ScoreBreakdown, SelfAudit, SourceReference, TopicCandidate
from linkedin_content_agent.validation import validate_generated_content, validate_originality


class ValidationTests(unittest.TestCase):
    def _valid_monday_content(self) -> GeneratedContent:
        primary = PostPackage(
            day="Monday",
            post_type="Build / Experiment",
            hook="I thought the LLM cleaning pass would remove edge cases. It exposed new ones instead.",
            core_idea=[
                "The first pass broke when schema drift hit nested records.",
                "The surprising result was that retrieval cues mattered more than prompt length.",
                "The lesson: treat cleanup as a pipeline tradeoff, not a one-shot prompt.",
            ],
            draft_post=(
                "I tried using an LLM to clean a messy support dataset.\n"
                "What broke was the schema assumption around nested fields.\n"
                "The surprising result: shorter prompts plus retrieval context beat the longer baseline.\n"
                "Lesson learned: the real tradeoff is control versus speed."
            ),
            visual_suggestion="Before/after screenshot of the dataset plus one failed row example.",
            why_this_works="It anchors the post in a concrete LLM workflow mistake and a clear lesson.",
            source_refs=[SourceReference(source="reddit:MachineLearning", title="Test source", url="https://example.com")],
            self_audit=SelfAudit(passed_checks=["Contains a mistake, result, and lesson."], critic_notes=[]),
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
        return GeneratedContent(primary=primary, backups=backups, selected_topic_reason="Strong builder signal.")

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


if __name__ == "__main__":
    unittest.main()
