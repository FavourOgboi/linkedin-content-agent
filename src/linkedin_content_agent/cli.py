from __future__ import annotations

import argparse
import json
import sys

from linkedin_content_agent.config import AppConfig
from linkedin_content_agent.models import RunOptions
from linkedin_content_agent.pipeline import ContentAgent, record_review
from linkedin_content_agent.storage import LocalHybridStorage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LinkedIn Content Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the content generation pipeline.")
    run_parser.add_argument("--day", dest="day_override")
    run_parser.add_argument("--topic", dest="topic_override")
    run_parser.add_argument(
        "--post-type",
        dest="post_type_override",
        choices=["insight", "relatable", "commentary", "teaching", "inspiration"],
    )
    run_parser.add_argument(
        "--format",
        dest="format_override",
        choices=["text", "photo", "screenshot", "carousel", "infographic"],
    )
    run_parser.add_argument("--skip-email", action="store_true")

    review_parser = subparsers.add_parser("review", help="Record a review decision for a previous run.")
    review_parser.add_argument("--run-id", required=True)
    review_parser.add_argument("--decision", required=True, choices=["approved", "rejected"])
    review_parser.add_argument("--notes", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.from_env()

    if args.command == "review":
        storage = LocalHybridStorage(config.data_dir)
        review = record_review(
            storage,
            run_id=args.run_id,
            decision=args.decision,
            notes=args.notes,
        )
        print(json.dumps({"run_id": review.run_id, "decision": review.decision, "notes": review.notes}, indent=2))
        return 0

    agent = ContentAgent.from_config(config)
    result = agent.run(
        RunOptions(
            day_override=args.day_override,
            topic_override=args.topic_override,
            post_type_override=args.post_type_override,
            format_override=args.format_override,
            send_email=not args.skip_email,
        )
    )
    print(
        json.dumps(
            {
                "run_id": result.summary.run_id,
                "status": result.summary.status,
                "selected_topic": result.summary.selected_topic,
                "delivery_status": result.delivery_result.status,
                "warnings": result.warnings,
                "artifacts": {
                    "json": str(result.artifacts.json_path),
                    "markdown": str(result.artifacts.markdown_path),
                    "prompt": str(result.artifacts.prompt_path),
                    "sqlite": str(result.artifacts.sqlite_path),
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
