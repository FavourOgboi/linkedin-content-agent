from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pathlib import Path
import unittest

from urllib.error import HTTPError

from linkedin_content_agent.models import CommentInsight, ScoreBreakdown, SourceReference, TopicCandidate, TopicContext, TopicDossier, TruthProfile
from linkedin_content_agent.sources import HNCommentSource, RedditCommentSource, RedditHotSource, parse_feed_bytes, parse_reddit_json, summarize_comments


FIXTURES = Path(__file__).parent / "fixtures"


class SourceParserTests(unittest.TestCase):
    def test_parse_rss_feed(self) -> None:
        payload = (FIXTURES / "feeds" / "sample_rss.xml").read_bytes()
        signals = parse_feed_bytes(payload, source_name="rss:test")
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0].title, "Why agent evals fail quietly")
        self.assertEqual(signals[0].source, "rss:test")

    def test_parse_atom_feed(self) -> None:
        payload = (FIXTURES / "feeds" / "sample_atom.xml").read_bytes()
        signals = parse_feed_bytes(payload, source_name="youtube:test-channel")
        self.assertEqual(len(signals), 2)
        self.assertIn("tool calling", signals[0].title.lower())
        self.assertTrue(signals[0].url.startswith("https://www.youtube.com/watch"))

    def test_parse_reddit_json(self) -> None:
        payload = (FIXTURES / "reddit" / "sample_hot.json").read_bytes()
        signals = parse_reddit_json(payload, subreddit="MachineLearning")
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0].source, "reddit:MachineLearning")
        self.assertGreater(signals[0].engagement_hint["score"], 0)

    def test_reddit_source_falls_back_to_rss_when_json_is_blocked(self) -> None:
        rss_payload = (FIXTURES / "reddit" / "sample_hot_rss.xml").read_bytes()

        def loader(url: str) -> bytes:
            if url.endswith("hot.json?limit=2"):
                raise HTTPError(url, 403, "Blocked", hdrs=None, fp=None)
            if url.endswith(".rss"):
                return rss_payload
            raise AssertionError(f"Unexpected URL: {url}")

        source = RedditHotSource("MachineLearning", limit=2, loader=loader)
        signals = source.fetch()
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0].source, "reddit:MachineLearning")
        self.assertIn("agent evals", signals[0].title.lower())

    def _topic_context(self, reference: SourceReference) -> TopicContext:
        candidate = TopicCandidate(
            title=reference.title,
            score_total=1.0,
            score_breakdown=ScoreBreakdown(1.0, 1.0, 1.0, 1.0, 0.0, 4.0),
            day_fit="strong",
            evidence=["test evidence"],
            angles=["commentary"],
            novelty_penalty=0.0,
            supporting_signals=[reference],
        )
        dossier = TopicDossier(
            topic_title=reference.title,
            primary_signal=reference,
            sources=[],
            source_count=1,
            claim_summaries=[reference.title],
            consensus_summary="test",
            disagreement_notes=[],
            stronger_source_present=False,
            weak_signal_echo=False,
        )
        truth_profile = TruthProfile(
            source_ownership="second_hand",
            evidence_strength="medium",
            risk_level="medium",
            authority_mode="amplifier",
            position="refine",
            conflict_level="low",
            provenance_rule="Attribute to external sources.",
            allowed_claim_posture="Interpret the signal.",
            required_copy_moves=[],
            forbidden_moves=[],
            allows_first_person_experiment=False,
            requires_explicit_provenance=True,
            allows_exact_metrics=False,
        )
        return TopicContext(candidate=candidate, dossier=dossier, truth_profile=truth_profile, creator_post_type="commentary")

    def test_summarize_comments_returns_structured_insight(self) -> None:
        insight = summarize_comments(
            source="reddit:MachineLearning",
            comments=[
                "This looks great, but it breaks once the schema gets messy.",
                "In practice the real issue is cost, not quality.",
                "Why does nobody benchmark the workflow boundary itself?",
            ],
        )
        self.assertIsInstance(insight, CommentInsight)
        self.assertEqual(insight.source, "reddit:MachineLearning")
        self.assertGreaterEqual(len(insight.key_debates), 1)

    def test_reddit_comment_source_harvests_public_json(self) -> None:
        payload = (FIXTURES / "reddit" / "sample_comments.json").read_bytes()

        def loader(url: str) -> bytes:
            self.assertIn(".json", url)
            return payload

        reference = SourceReference(
            source="reddit:MachineLearning",
            title="What people get wrong about evals",
            url="https://www.reddit.com/r/MachineLearning/comments/abc123/what_people_get_wrong_about_agent_evals/",
        )
        topic_context = self._topic_context(reference)
        insight = RedditCommentSource(loader=loader).fetch(topic_context)
        self.assertIsNotNone(insight)
        self.assertEqual(insight.source, "reddit:MachineLearning")
        self.assertGreaterEqual(insight.comment_count, 2)

    def test_hn_comment_source_harvests_story_and_comments(self) -> None:
        story_payload = (FIXTURES / "hn" / "story_item.json").read_bytes()
        comment_one = (FIXTURES / "hn" / "comment_1.json").read_bytes()
        comment_two = (FIXTURES / "hn" / "comment_2.json").read_bytes()

        def loader(url: str) -> bytes:
            if "algolia" in url:
                return (FIXTURES / "hn" / "algolia_search.json").read_bytes()
            if url.endswith("/item/123.json"):
                return story_payload
            if url.endswith("/item/1001.json"):
                return comment_one
            if url.endswith("/item/1002.json"):
                return comment_two
            raise AssertionError(f"Unexpected URL: {url}")

        reference = SourceReference(
            source="hackernews",
            title="A practical memory pattern for agents",
            url="https://example.com/agent-memory",
        )
        topic_context = self._topic_context(reference)
        insight = HNCommentSource(loader=loader).fetch(topic_context)
        self.assertIsNotNone(insight)
        self.assertEqual(insight.source, "hackernews")
        self.assertGreaterEqual(insight.comment_count, 2)


if __name__ == "__main__":
    unittest.main()
