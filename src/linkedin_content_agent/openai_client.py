from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any, Protocol

from linkedin_content_agent.config import AppConfig
from linkedin_content_agent.day_contracts import DayContract
from linkedin_content_agent.json_schemas import AUDIT_RESULT_SCHEMA, GENERATION_PAYLOAD_SCHEMA, TOPIC_SELECTION_SCHEMA
from linkedin_content_agent.models import BackupIdea, GeneratedContent, ModelAuditResult, PostPackage, SelfAudit, SourceReference, TopicCandidate, TopicSelection


CONTENT_SYSTEM_PROMPT = """
You are an elite LinkedIn content strategist for a data/AI builder transitioning into AI systems, LLMs, and agents.

Your job is not to write generic posts.
Your job is to generate high-signal, experience-driven content ideas and drafts that reflect real thinking, experimentation, and insight.

Rules:
- No generic motivation
- No basic explanations
- No AI-copyable fluff
- Every idea must include at least one of: mistake, insight, unexpected result, tradeoff
- Tone: clear, sharp, intelligent
- No emojis
- No hype language
- If a beginner or shallow AI could produce it, reject it internally and improve it
""".strip()


class ContentModel(Protocol):
    def choose_topic(self, contract: DayContract, candidates: list[TopicCandidate], topic_override: str | None = None) -> TopicSelection:
        raise NotImplementedError

    def generate_content(
        self,
        *,
        contract: DayContract,
        selection: TopicSelection,
        candidates: list[TopicCandidate],
        creator_context: str,
        revision_feedback: str | None = None,
    ) -> GeneratedContent:
        raise NotImplementedError

    def audit_content(
        self,
        *,
        contract: DayContract,
        generated_content: GeneratedContent,
        deterministic_issues: list[str],
    ) -> ModelAuditResult:
        raise NotImplementedError


class OpenAIContentModel:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required to run the content agent.")
        from openai import OpenAI

        self._client = OpenAI(api_key=self.config.openai_api_key)
        return self._client

    def _structured_call(
        self,
        *,
        schema_name: str,
        schema: dict[str, Any],
        system_prompt: str,
        user_prompt: str,
        reasoning_effort: str,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = client.responses.create(
            model=self.config.openai_model,
            reasoning={"effort": reasoning_effort},
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
        )

        output_text = getattr(response, "output_text", None)
        if not output_text:
            output = getattr(response, "output", []) or []
            for item in output:
                for content in getattr(item, "content", []) or []:
                    text = getattr(content, "text", None)
                    if text:
                        output_text = text
                        break
                if output_text:
                    break
        if not output_text:
            raise RuntimeError("OpenAI response did not contain output text.")
        return json.loads(output_text)

    def choose_topic(self, contract: DayContract, candidates: list[TopicCandidate], topic_override: str | None = None) -> TopicSelection:
        if topic_override:
            backups = [candidate.title for candidate in candidates if candidate.title != topic_override][:2]
            return TopicSelection(
                selected_title=topic_override.strip(),
                selected_reason="Manual topic override supplied by the operator.",
                backup_titles=backups,
                caution_notes=[],
            )
        if not candidates:
            raise RuntimeError("No candidates available for topic selection.")

        prompt = "\n".join(
            [
                f"Today's contract: {contract.day} - {contract.post_type}",
                f"Description: {contract.description}",
                f"Requirements: {', '.join(contract.requirements)}",
                "",
                "Select the strongest topic for authority building and nominate two backups.",
                "The answer must prefer topics that feel practical, slightly opinionated, and grounded in real scenarios.",
                "",
                json.dumps([asdict(candidate) for candidate in candidates[:8]], indent=2),
            ]
        )
        try:
            payload = self._structured_call(
                schema_name="topic_selection",
                schema=TOPIC_SELECTION_SCHEMA,
                system_prompt=CONTENT_SYSTEM_PROMPT,
                user_prompt=prompt,
                reasoning_effort=self.config.selection_reasoning,
            )
            return TopicSelection(**payload)
        except Exception:
            return TopicSelection(
                selected_title=candidates[0].title,
                selected_reason="Fell back to the highest-scoring deterministic candidate.",
                backup_titles=[candidate.title for candidate in candidates[1:3]],
                caution_notes=["Topic selection model call failed; deterministic fallback used."],
            )

    def generate_content(
        self,
        *,
        contract: DayContract,
        selection: TopicSelection,
        candidates: list[TopicCandidate],
        creator_context: str,
        revision_feedback: str | None = None,
    ) -> GeneratedContent:
        prompt_parts = [
            creator_context,
            f"Today is {contract.day}. The post type is {contract.post_type}.",
            f"Contract description: {contract.description}",
            f"Mandatory requirements: {', '.join(contract.requirements)}",
            "",
            f"Selected topic: {selection.selected_title}",
            f"Why selected: {selection.selected_reason}",
            "",
            "Reference candidates:",
            json.dumps([asdict(candidate) for candidate in candidates[:5]], indent=2),
            "",
            "Return one primary post package and exactly two backup ideas.",
            "The primary post must use the exact output structure. It must not sound motivational or generic.",
        ]
        if revision_feedback:
            prompt_parts.extend(["", "Revision feedback from the critic:", revision_feedback])

        payload = self._structured_call(
            schema_name="generation_payload",
            schema=GENERATION_PAYLOAD_SCHEMA,
            system_prompt=CONTENT_SYSTEM_PROMPT,
            user_prompt="\n".join(prompt_parts),
            reasoning_effort=self.config.generation_reasoning,
        )
        primary_payload = payload["primary"]
        primary = PostPackage(
            day=primary_payload["day"],
            post_type=primary_payload["post_type"],
            hook=primary_payload["hook"],
            core_idea=list(primary_payload["core_idea"]),
            draft_post=primary_payload["draft_post"],
            visual_suggestion=primary_payload["visual_suggestion"],
            why_this_works=primary_payload["why_this_works"],
            source_refs=[SourceReference(**item) for item in primary_payload["source_refs"]],
            self_audit=SelfAudit(**primary_payload["self_audit"]),
        )
        backups = [BackupIdea(**backup) for backup in payload["backups"]]
        return GeneratedContent(
            primary=primary,
            backups=backups,
            selected_topic_reason=payload["selected_topic_reason"],
        )

    def audit_content(
        self,
        *,
        contract: DayContract,
        generated_content: GeneratedContent,
        deterministic_issues: list[str],
    ) -> ModelAuditResult:
        prompt = "\n".join(
            [
                f"Audit this {contract.day} / {contract.post_type} content package.",
                "Fail it if it sounds generic, beginner-level, or AI-obvious.",
                "Fail it if it does not genuinely satisfy the contract.",
                "",
                "Deterministic issues already found:",
                json.dumps(deterministic_issues, indent=2),
                "",
                "Generated content:",
                json.dumps(asdict(generated_content), indent=2),
            ]
        )
        payload = self._structured_call(
            schema_name="audit_result",
            schema=AUDIT_RESULT_SCHEMA,
            system_prompt=CONTENT_SYSTEM_PROMPT,
            user_prompt=prompt,
            reasoning_effort=self.config.audit_reasoning,
        )
        return ModelAuditResult(**payload)
