from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pathlib import Path
import unittest

from linkedin_content_agent.sources import parse_feed_bytes, parse_reddit_json


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


if __name__ == "__main__":
    unittest.main()
