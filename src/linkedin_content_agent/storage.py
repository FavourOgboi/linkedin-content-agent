from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
from typing import Any

from linkedin_content_agent.models import DeliveryResult, GeneratedContent, ReviewRecord, RunArtifacts, RunContext, RunSummary, Signal, TopicCandidate
from linkedin_content_agent.rendering import render_markdown
from linkedin_content_agent.utils import append_jsonl, ensure_directory, load_json, write_json


class StorageBackend(ABC):
    @abstractmethod
    def load_recent_topic_titles(self, *, limit: int = 200) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def load_recent_runs(self, *, n: int = 4) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def save_run(
        self,
        *,
        context: RunContext,
        selected_topic: str,
        generated_content: GeneratedContent,
        candidates: list[TopicCandidate],
        signals: list[Signal],
        delivery_result: DeliveryResult,
        warnings: list[str],
        prompt_payload: dict[str, Any],
        creator_post_type: str,
        topic_pillar: str,
        content_format: str,
        comment_insight_used: bool = False,
        audit_skipped: bool = False,
        audit_skip_reason: str | None = None,
        review_url: str | None = None,
    ) -> tuple[RunSummary, RunArtifacts]:
        raise NotImplementedError

    @abstractmethod
    def record_review(self, review: ReviewRecord) -> None:
        raise NotImplementedError


class LocalHybridStorage(StorageBackend):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.history_dir = ensure_directory(root / "history")
        self.outputs_dir = ensure_directory(root / "outputs")
        self.prompts_dir = ensure_directory(root / "prompts")
        self.artifacts_dir = ensure_directory(root / "artifacts")
        self.index_path = self.history_dir / "index.json"
        self.runs_path = self.history_dir / "runs.jsonl"
        self.reviews_path = self.history_dir / "reviews.jsonl"
        self.sqlite_path = self.artifacts_dir / "content_agent_cache.db"
        self._initialize_files()
        self._ensure_schema()

    def _initialize_files(self) -> None:
        if not self.index_path.exists():
            write_json(self.index_path, {})
        for path in (self.runs_path, self.reviews_path):
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    day TEXT NOT NULL,
                    post_type TEXT NOT NULL,
                    creator_post_type TEXT NOT NULL DEFAULT '',
                    topic_pillar TEXT NOT NULL DEFAULT '',
                    content_format TEXT NOT NULL DEFAULT 'text',
                    selected_topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    delivery_status TEXT NOT NULL,
                    source_count INTEGER NOT NULL,
                    primary_artifact TEXT NOT NULL,
                    prompt_artifact TEXT NOT NULL,
                    audit_skipped INTEGER NOT NULL DEFAULT 0,
                    audit_skip_reason TEXT,
                    warnings_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT,
                    engagement_hint_json TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    raw_metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS topic_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    score_total REAL NOT NULL,
                    day_fit TEXT NOT NULL,
                    novelty_penalty REAL NOT NULL,
                    score_breakdown_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    angles_json TEXT NOT NULL,
                    supporting_signals_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    run_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    decided_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(connection, "runs", "creator_post_type", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "runs", "topic_pillar", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "runs", "content_format", "TEXT NOT NULL DEFAULT 'text'")
            self._ensure_column(connection, "runs", "audit_skipped", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "runs", "audit_skip_reason", "TEXT")

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in columns:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def load_recent_topic_titles(self, *, limit: int = 200) -> list[str]:
        index = load_json(self.index_path, {})
        ordered = sorted(index.values(), key=lambda item: item.get("created_at", ""), reverse=True)
        return [item["selected_topic"] for item in ordered[:limit] if item.get("selected_topic")]

    def load_recent_runs(self, *, n: int = 4) -> list[dict[str, Any]]:
        if not self.runs_path.exists():
            return []
        lines = [line.strip() for line in self.runs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        recent: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                recent.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(recent) >= n:
                break
        return recent

    def save_run(
        self,
        *,
        context: RunContext,
        selected_topic: str,
        generated_content: GeneratedContent,
        candidates: list[TopicCandidate],
        signals: list[Signal],
        delivery_result: DeliveryResult,
        warnings: list[str],
        prompt_payload: dict[str, Any],
        creator_post_type: str,
        topic_pillar: str,
        content_format: str,
        comment_insight_used: bool = False,
        audit_skipped: bool = False,
        audit_skip_reason: str | None = None,
        review_url: str | None = None,
    ) -> tuple[RunSummary, RunArtifacts]:
        json_path = self.outputs_dir / f"{context.run_id}.json"
        markdown_path = self.outputs_dir / f"{context.run_id}.md"
        prompt_path = self.prompts_dir / f"{context.run_id}.json"

        summary = RunSummary(
            run_id=context.run_id,
            created_at=context.created_at.isoformat(),
            day=context.day,
            post_type=context.post_type,
            creator_post_type=creator_post_type,
            topic_pillar=topic_pillar,
            content_format=content_format,
            selected_topic=selected_topic,
            status="awaiting_review",
            source_count=len(signals),
            delivery_status=delivery_result.status,
            primary_artifact=str(json_path),
            prompt_artifact=str(prompt_path),
            backup_titles=[backup.title for backup in generated_content.backups],
            comment_insight_used=comment_insight_used,
            audit_skipped=audit_skipped,
            audit_skip_reason=audit_skip_reason,
            warnings=warnings,
        )

        index = load_json(self.index_path, {})
        index[context.run_id] = asdict(summary)
        write_json(self.index_path, index)
        append_jsonl(self.runs_path, asdict(summary))

        output_payload = {
            "summary": asdict(summary),
            "generated_content": asdict(generated_content),
            "review_url": review_url,
            "warnings": warnings,
            "candidates": [asdict(candidate) for candidate in candidates],
            "signals": [asdict(signal) for signal in signals],
            "delivery_result": asdict(delivery_result),
        }
        write_json(json_path, output_payload)
        markdown_path.write_text(render_markdown(summary, generated_content, review_url), encoding="utf-8")
        write_json(prompt_path, prompt_payload)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, created_at, day, post_type, creator_post_type, topic_pillar, content_format, selected_topic, status,
                    delivery_status, source_count, primary_artifact, prompt_artifact, audit_skipped, audit_skip_reason, warnings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.run_id,
                    summary.created_at,
                    summary.day,
                    summary.post_type,
                    summary.creator_post_type,
                    summary.topic_pillar,
                    summary.content_format,
                    summary.selected_topic,
                    summary.status,
                    summary.delivery_status,
                    summary.source_count,
                    summary.primary_artifact,
                    summary.prompt_artifact,
                    1 if summary.audit_skipped else 0,
                    summary.audit_skip_reason,
                    json.dumps(summary.warnings),
                ),
            )
            connection.executemany(
                """
                INSERT INTO signals (
                    run_id, source, title, url, published_at, engagement_hint_json, excerpt, raw_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        summary.run_id,
                        signal.source,
                        signal.title,
                        signal.url,
                        signal.published_at,
                        json.dumps(signal.engagement_hint),
                        signal.excerpt,
                        json.dumps(signal.raw_metadata),
                    )
                    for signal in signals
                ],
            )
            connection.executemany(
                """
                INSERT INTO topic_candidates (
                    run_id, title, score_total, day_fit, novelty_penalty, score_breakdown_json,
                    evidence_json, angles_json, supporting_signals_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        summary.run_id,
                        candidate.title,
                        candidate.score_total,
                        candidate.day_fit,
                        candidate.novelty_penalty,
                        json.dumps(asdict(candidate.score_breakdown)),
                        json.dumps(candidate.evidence),
                        json.dumps(candidate.angles),
                        json.dumps([asdict(reference) for reference in candidate.supporting_signals]),
                    )
                    for candidate in candidates
                ],
            )

        artifacts = RunArtifacts(
            json_path=json_path,
            markdown_path=markdown_path,
            prompt_path=prompt_path,
            sqlite_path=self.sqlite_path,
        )
        return summary, artifacts

    def record_review(self, review: ReviewRecord) -> None:
        index = load_json(self.index_path, {})
        if review.run_id not in index:
            raise KeyError(f"Unknown run ID: {review.run_id}")

        append_jsonl(self.reviews_path, asdict(review))
        record = index[review.run_id]
        record["status"] = review.decision
        record["review_notes"] = review.notes
        record["reviewed_at"] = review.decided_at
        write_json(self.index_path, index)

        output_path = self.outputs_dir / f"{review.run_id}.json"
        if output_path.exists():
            payload = load_json(output_path, {})
            payload["summary"]["status"] = review.decision
            payload["review"] = asdict(review)
            write_json(output_path, payload)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO reviews (run_id, decision, notes, decided_at)
                VALUES (?, ?, ?, ?)
                """,
                (review.run_id, review.decision, review.notes, review.decided_at),
            )
            connection.execute("UPDATE runs SET status = ? WHERE run_id = ?", (review.decision, review.run_id))
