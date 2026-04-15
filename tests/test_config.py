from pathlib import Path
import os
import shutil
import sys
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from linkedin_content_agent.config import AppConfig, load_dotenv_file


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = ROOT / "tests" / "_tmp" / f"config-{uuid4().hex}"
        self.temp_root.mkdir(parents=True, exist_ok=False)
        self.dotenv_path = self.temp_root / ".env"

    def tearDown(self) -> None:
        for key in ("OPENAI_API_KEY", "LCA_OPENAI_MODEL", "LCA_REDDIT_SUBREDDITS"):
            os.environ.pop(key, None)
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_load_dotenv_file_populates_missing_values(self) -> None:
        self.dotenv_path.write_text(
            "OPENAI_API_KEY=test-key\nLCA_OPENAI_MODEL=gpt-5.1\n",
            encoding="utf-8",
        )

        load_dotenv_file(self.dotenv_path)

        self.assertEqual(os.environ["OPENAI_API_KEY"], "test-key")
        self.assertEqual(os.environ["LCA_OPENAI_MODEL"], "gpt-5.1")

    def test_load_dotenv_file_does_not_override_existing_env(self) -> None:
        os.environ["OPENAI_API_KEY"] = "existing-key"
        self.dotenv_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")

        load_dotenv_file(self.dotenv_path)

        self.assertEqual(os.environ["OPENAI_API_KEY"], "existing-key")

    def test_blank_reddit_config_disables_reddit_sources(self) -> None:
        self.dotenv_path.write_text("LCA_REDDIT_SUBREDDITS=\n", encoding="utf-8")

        load_dotenv_file(self.dotenv_path)
        config = AppConfig.from_env()

        self.assertEqual(config.reddit_subreddits, ())


if __name__ == "__main__":
    unittest.main()
