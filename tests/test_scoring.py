from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from datetime import UTC, datetime, timedelta
import unittest

from linkedin_content_agent.day_contracts import resolve_day_contract
from linkedin_content_agent.models import Signal
from linkedin_content_agent.scoring import build_candidate, rank_signals


class ScoringTests(unittest.TestCase):
    def test_reddit_signal_with_relevant_keywords_scores_higher(self) -> None:
        now = datetime.now(UTC)
        recent_reddit = Signal(
            source="reddit:MachineLearning",
            title="Unexpected tradeoff in agent eval pipelines",
            url="https://example.com/reddit",
            published_at=now.isoformat(),
            engagement_hint={"score": 120, "num_comments": 34},
            excerpt="A builder shared why their LLM eval workflow looked correct but failed in production.",
            raw_metadata={},
        )
        older_rss = Signal(
            source="rss:https://example.com/feed",
            title="Insight from a slower data workflow experiment",
            url="https://example.com/rss",
            published_at=(now - timedelta(days=9)).isoformat(),
            engagement_hint={},
            excerpt="A lower-signal insight about data workflow tradeoffs without much engagement.",
            raw_metadata={},
        )
        contract = resolve_day_contract("Monday")
        candidates = rank_signals([older_rss, recent_reddit], contract, prior_titles=[])
        self.assertEqual(candidates[0].title, recent_reddit.title)
        self.assertGreater(candidates[0].score_total, candidates[1].score_total)

    def test_novelty_penalty_applies_to_repeated_titles(self) -> None:
        signal = Signal(
            source="reddit:LocalLLaMA",
            title="LLM schema design tradeoffs",
            url="https://example.com/topic",
            published_at=datetime.now(UTC).isoformat(),
            engagement_hint={"score": 10},
            excerpt="Tradeoffs in schema design for structured outputs.",
            raw_metadata={},
        )
        contract = resolve_day_contract("Thursday")
        candidate = build_candidate(signal, contract, prior_titles=["LLM schema design tradeoffs"])
        self.assertIsNotNone(candidate)
        self.assertGreater(candidate.novelty_penalty, 0.0)

    def test_irrelevant_signal_is_filtered_out(self) -> None:
        signal = Signal(
            source="hackernews",
            title="Don't feel like exercising? Maybe it's the wrong time of day for you",
            url="https://example.com/exercise",
            published_at=datetime.now(UTC).isoformat(),
            engagement_hint={},
            excerpt="A lifestyle article about exercise timing.",
            raw_metadata={},
        )
        contract = resolve_day_contract("Wednesday")
        candidate = build_candidate(signal, contract, prior_titles=[])
        self.assertIsNone(candidate)


if __name__ == "__main__":
    unittest.main()
