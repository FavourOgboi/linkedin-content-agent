from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from linkedin_content_agent.validation import check_hook_discipline, check_labeled_paragraphs


class HookDisciplineTests(unittest.TestCase):
    def test_saw_a_fails_for_teaching(self) -> None:
        issues = check_hook_discipline("Saw a neat HN project today that hit a nerve.\n\nRest of post.", "teaching")
        self.assertTrue(issues)

    def test_i_saw_fails_for_insight(self) -> None:
        issues = check_hook_discipline("I saw a really interesting pattern this week.\n\nRest of post.", "insight")
        self.assertTrue(issues)

    def test_i_read_fails_for_inspiration(self) -> None:
        issues = check_hook_discipline("I read something this morning that changed how I think.\n\nRest.", "inspiration")
        self.assertTrue(issues)

    def test_today_i_fails_for_relatable(self) -> None:
        issues = check_hook_discipline("Today I found a project that made me rethink everything.\n\nRest.", "relatable")
        self.assertTrue(issues)

    def test_there_is_a_new_fails_for_teaching(self) -> None:
        issues = check_hook_discipline("There's a new framework that handles agent memory differently.\n\nRest.", "teaching")
        self.assertTrue(issues)

    def test_tension_hook_passes_for_teaching(self) -> None:
        issues = check_hook_discipline("Most people wire up a vector DB before they need one.\n\nRest.", "teaching")
        self.assertEqual(issues, [])

    def test_mistake_hook_passes_for_insight(self) -> None:
        issues = check_hook_discipline("The hardest part of data engineering is rarely the pipeline itself.\n\nRest.", "insight")
        self.assertEqual(issues, [])

    def test_surprise_hook_passes_for_relatable(self) -> None:
        issues = check_hook_discipline(
            "Six months of learning Python. Still googling how to reverse a list.\n\nRest.",
            "relatable",
        )
        self.assertEqual(issues, [])

    def test_short_inspiration_hook_passes(self) -> None:
        issues = check_hook_discipline("You could not explain what an API was three months ago.\n\nRest.", "inspiration")
        self.assertEqual(issues, [])

    def test_commentary_source_first_with_tension_passes(self) -> None:
        issues = check_hook_discipline(
            "Google just killed its open model program, and nobody is asking why.\n\nRest.",
            "commentary",
        )
        self.assertEqual(issues, [])

    def test_commentary_source_first_without_tension_fails(self) -> None:
        issues = check_hook_discipline("Today I read that Google released a new model.\n\nRest.", "commentary")
        self.assertTrue(issues)


class LabeledParagraphTests(unittest.TestCase):
    def test_takeaway_label_fails(self) -> None:
        issues = check_labeled_paragraphs("Good hook.\n\nSome content.\n\nTakeaway: do the simple thing first.")
        self.assertTrue(issues)

    def test_common_mistake_label_fails(self) -> None:
        issues = check_labeled_paragraphs("Good hook.\n\nCommon mistake: reaching for vectors too early.")
        self.assertTrue(issues)

    def test_why_this_works_label_fails(self) -> None:
        issues = check_labeled_paragraphs("Good hook.\n\nWhy this works: plain text is portable.")
        self.assertTrue(issues)

    def test_tradeoff_label_fails(self) -> None:
        issues = check_labeled_paragraphs("Good hook.\n\nTradeoff: BM25 misses fuzzy matches.")
        self.assertTrue(issues)

    def test_tldr_label_fails(self) -> None:
        issues = check_labeled_paragraphs("Good hook.\n\nTL;DR: start simple, add complexity later.")
        self.assertTrue(issues)

    def test_multiple_labels_all_caught(self) -> None:
        issues = check_labeled_paragraphs(
            "Good hook.\n\nCommon mistake: over-engineering.\n\nTakeaway: keep it boring.\n\nWhy this works: simple is debuggable."
        )
        self.assertEqual(len(issues), 3)

    def test_clean_flowing_post_passes(self) -> None:
        issues = check_labeled_paragraphs(
            "Most people wire up a vector DB before they need one.\n\n"
            "If your knowledge base is small and curated, plain keyword "
            "search finds the right answer most of the time.\n\n"
            "Start with boring storage. Add complexity only when the "
            "simple thing is clearly in pain."
        )
        self.assertEqual(issues, [])

    def test_colon_in_body_not_flagged(self) -> None:
        issues = check_labeled_paragraphs(
            "The pattern is simple: markdown files, Git history, BM25 search.\n\n"
            "That combination handles most small agent backends just fine."
        )
        self.assertEqual(issues, [])

    def test_code_snippet_colon_not_flagged(self) -> None:
        issues = check_labeled_paragraphs(
            "One line of Python tells the whole story:\n\n"
            "`agent.read(file) -> answer -> agent.commit(edit)`\n\n"
            "No orchestration framework. No message bus."
        )
        self.assertEqual(issues, [])


class CombinedVoiceValidationTests(unittest.TestCase):
    def test_post_with_both_failures_caught(self) -> None:
        post = "Saw a neat HN project today.\n\nCommon mistake: reaching for a vector DB too early.\n\nTakeaway: start with plain text."
        hook_issues = check_hook_discipline(post, "teaching")
        label_issues = check_labeled_paragraphs(post)
        self.assertTrue(hook_issues)
        self.assertEqual(len(label_issues), 2)

    def test_clean_post_passes_both_checks(self) -> None:
        post = (
            "Most people over-engineer their first AI backend.\n\n"
            "Plain markdown files in Git with a BM25 index on top handles most small projects just fine.\n\n"
            "Saw a clean implementation of this on HN this week. Worth knowing the pattern exists before you reach for the heavy stack.\n\n"
            "#Python #LLM #Backend"
        )
        hook_issues = check_hook_discipline(post, "teaching")
        label_issues = check_labeled_paragraphs(post)
        self.assertEqual(hook_issues, [])
        self.assertEqual(label_issues, [])


if __name__ == "__main__":
    unittest.main()
