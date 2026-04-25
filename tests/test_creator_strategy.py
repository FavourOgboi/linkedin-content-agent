from pathlib import Path
from datetime import date
import shutil
import sys
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from linkedin_content_agent.content_strategy import (
    POST_TYPE_WEIGHTS,
    get_evidence_policy,
    get_length_policy,
    get_originality_threshold,
    normalize_creator_post_type,
    passes_topic_filter,
    select_content_format,
    select_post_type,
)
from linkedin_content_agent.models import (
    BackupIdea,
    GeneratedContent,
    ImageSuggestion,
    PostPackage,
    RunSummary,
    SelfAudit,
    SourceReference,
)
from linkedin_content_agent.openai_client import build_system_prompt, normalize_originality_score
from linkedin_content_agent.rendering import render_markdown
from linkedin_content_agent.storage import LocalHybridStorage
from linkedin_content_agent.validation import check_post_length, check_readability


class CreatorStrategyTests(unittest.TestCase):
    def test_same_date_produces_stable_post_type(self) -> None:
        result_one = select_post_type("Tuesday", recent_types=["insight"], seed_date=date(2026, 4, 25))
        result_two = select_post_type("Tuesday", recent_types=["insight"], seed_date=date(2026, 4, 25))
        self.assertEqual(result_one, result_two)

    def test_day_weights_return_valid_type(self) -> None:
        for day_name in POST_TYPE_WEIGHTS:
            result = select_post_type(day_name, recent_types=[], seed_date=date(2026, 4, 25))
            self.assertIn(result, POST_TYPE_WEIGHTS[day_name])

    def test_same_date_produces_stable_content_format(self) -> None:
        result_one = select_content_format("Tuesday", recent_formats=["text"], seed_date=date(2026, 4, 25))
        result_two = select_content_format("Tuesday", recent_formats=["text"], seed_date=date(2026, 4, 25))
        self.assertEqual(result_one, result_two)

    def test_on_brand_signal_passes_filter(self) -> None:
        self.assertTrue(passes_topic_filter("How to build a data pipeline with Airflow and dbt"))

    def test_off_brand_signal_fails_filter(self) -> None:
        self.assertFalse(passes_topic_filter("Latest updates to Rust's memory model"))

    def test_commentary_requires_source_policy(self) -> None:
        policy = get_evidence_policy("commentary")
        self.assertTrue(policy["requires_source"])

    def test_originality_threshold_lower_for_relatable(self) -> None:
        self.assertLess(get_originality_threshold("relatable"), get_originality_threshold("insight"))

    def test_length_policy_exposes_extended_mode_for_teaching(self) -> None:
        policy = get_length_policy("teaching")
        self.assertGreater(policy["extended"], policy["standard"])

    def test_build_system_prompt_includes_post_type_and_day_hint(self) -> None:
        prompt = build_system_prompt("insight", "Monday")
        self.assertIn("POST TYPE: INSIGHT", prompt)
        self.assertIn("TODAY'S TONE HINT", prompt)
        self.assertIn("HOOK DISCIPLINE", prompt)
        self.assertIn("INVISIBLE STRUCTURE", prompt)

    def test_readability_check_catches_corporate_language(self) -> None:
        issues = check_readability("We must leverage robust ecosystems to democratize seamless solutions.")
        self.assertTrue(issues)

    def test_post_length_over_ceiling_fails(self) -> None:
        issues = check_post_length(" ".join(["word"] * 200), "relatable", "standard", None)
        self.assertTrue(issues)

    def test_post_length_ignores_hashtag_lines(self) -> None:
        issues = check_post_length("Good hook.\n\nGood body.\n\n#Python #Data #AI", "inspiration", "standard", None)
        self.assertEqual(issues, [])

    def test_normalize_creator_post_type_maps_legacy_label(self) -> None:
        self.assertEqual(normalize_creator_post_type("Thinking / Reflection"), "inspiration")

    def test_normalize_originality_score_converts_fractional_scale(self) -> None:
        self.assertEqual(normalize_originality_score(0.74), 7.4)
        self.assertEqual(normalize_originality_score(8.2), 8.2)


class RenderingAndStorageTests(unittest.TestCase):
    def _workspace_run_dir(self) -> Path:
        base = ROOT / "tests" / "_tmp"
        base.mkdir(parents=True, exist_ok=True)
        run_dir = base / f"creator-{uuid4().hex}"
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def test_render_markdown_includes_structured_image_suggestion(self) -> None:
        summary = RunSummary(
            run_id="test-run",
            created_at="2026-04-25T00:00:00+00:00",
            day="Tuesday",
            post_type="Micro-Teach",
            creator_post_type="teaching",
            topic_pillar="python_backend",
            content_format="text",
            selected_topic="Why schema validation matters",
            status="awaiting_review",
            source_count=1,
            delivery_status="skipped",
            primary_artifact="output.json",
            prompt_artifact="prompt.json",
            backup_titles=["Backup one", "Backup two"],
            warnings=[],
        )
        content = GeneratedContent(
            primary=PostPackage(
                day="Tuesday",
                post_type="teaching",
                hook="Most bugs show up at the boundary, not in the function.",
                core_idea=[
                    "Schema validation catches bad assumptions early.",
                    "The insight is that narrow checks prevent wide downstream failures.",
                    "The tradeoff is a little setup for a lot less debugging.",
                ],
                draft_post="Validation is boring until it saves you three hours of debugging.",
                visual_suggestion="Simple terminal screenshot.",
                image_suggestion=ImageSuggestion(
                    type="screenshot",
                    description="A failing request beside the validated version.",
                    how_to_create="Show the bad payload and the corrected one side by side.",
                    why_it_works="It turns an abstract lesson into a recognizable debugging moment.",
                ),
                why_this_works="It teaches one concept plainly.",
                source_refs=[SourceReference(source="rss:test", title="Source", url="https://example.com")],
                self_audit=SelfAudit(passed_checks=["Clear and specific."], critic_notes=[]),
            ),
            backups=[
                BackupIdea(
                    title="Validation catches the boring bugs",
                    angle="teaching",
                    hook="The glamorous bug is rarely the real one.",
                    why_now="People still underinvest in validation.",
                    visual_suggestion="Code diff screenshot.",
                ),
                BackupIdea(
                    title="The boundary is where the bug lives",
                    angle="insight",
                    hook="Most broken systems fail at handoffs.",
                    why_now="More teams are composing tools and APIs together.",
                    visual_suggestion="Tiny sequence diagram.",
                ),
            ],
            selected_topic_reason="Strong creator-fit topic.",
        )

        markdown = render_markdown(summary, content)
        self.assertIn("Image suggestion (screenshot)", markdown)

    def test_storage_load_recent_runs_returns_newest_first(self) -> None:
        temp_dir = self._workspace_run_dir()
        try:
            storage = LocalHybridStorage(temp_dir / "data")
            storage.runs_path.write_text(
                "\n".join(
                    [
                        '{"run_id":"old","creator_post_type":"insight","topic_pillar":"ai_ml"}',
                        '{"run_id":"new","creator_post_type":"teaching","topic_pillar":"python_backend"}',
                    ]
                ),
                encoding="utf-8",
            )
            recent = storage.load_recent_runs(n=1)
            self.assertEqual(recent[0]["run_id"], "new")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
