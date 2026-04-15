from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from datetime import datetime
import unittest
from linkedin_content_agent.day_contracts import resolve_day_contract, resolve_topic_choice


class DayContractTests(unittest.TestCase):
    def test_day_override_takes_precedence(self) -> None:
        contract = resolve_day_contract("Monday")
        self.assertEqual(contract.day, "Monday")
        self.assertEqual(contract.post_type, "Build / Experiment")

    def test_resolves_from_datetime_when_no_override(self) -> None:
        current = datetime(2026, 4, 15, 8, 30)
        contract = resolve_day_contract(now=current, timezone="Africa/Lagos")
        self.assertEqual(contract.day, "Wednesday")
        self.assertEqual(contract.post_type, "Knowledge / Carousel")

    def test_topic_override_wins_over_candidate(self) -> None:
        self.assertEqual(
            resolve_topic_choice("Using LLMs for data cleaning", "Fallback topic"),
            "Using LLMs for data cleaning",
        )
        self.assertEqual(resolve_topic_choice(None, "Fallback topic"), "Fallback topic")


if __name__ == "__main__":
    unittest.main()
