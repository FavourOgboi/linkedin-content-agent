from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Protocol

from linkedin_content_agent.config import AppConfig
from linkedin_content_agent.content_strategy import (
    VOICE_PROFILE,
    get_day_tone_hint,
    get_evidence_policy,
    get_format_instruction,
    get_template,
)
from linkedin_content_agent.day_contracts import DayContract
from linkedin_content_agent.json_schemas import AUDIT_RESULT_SCHEMA, GENERATION_PAYLOAD_SCHEMA, ORIGINALITY_AUDIT_SCHEMA, TOPIC_SELECTION_SCHEMA
from linkedin_content_agent.models import (
    AuthorityMode,
    BackupIdea,
    CarouselSlide,
    FormatPlan,
    GeneratedContent,
    ImageSuggestion,
    ModelAuditResult,
    OriginalityAudit,
    PostPackage,
    SelfAudit,
    SourceReference,
    TopicContext,
    TopicSelection,
    SourceOwnership,
    EvidenceStrengthLabel,
)


BASE_VOICE_PROMPT = """
You are writing LinkedIn posts for a data and AI practitioner based in Nigeria who builds in public and teaches what they know.

Your job is not to sound like a journalist or a press release.
Your job is to write creator-first posts with a clear point of view, while staying honest about what is first-hand, second-hand, and still uncertain.

Hard rules:
- Short sentences. Simple words. No corporate speak.
- First person is welcome for opinions and interpretation.
- Never fake experiments, measurements, or certainty.
- External signals are inputs, not final framing.
- Do not reuse source headline framing or distinctive source phrasing.
- No generic motivation, no empty hype, no documentation voice.
- If the draft has nothing original to say, say less, not more.
- Keep the post easy to scan in one pass.

HOOK DISCIPLINE - enforced on every post:
- Line 1 must lead with tension, mistake, surprise, or human truth.
- Never: "Saw a...", "I saw...", "I read...", "I came across..."
- Never open with a source name, tool name, company name, or project name.
- The source belongs in passing, line 2 or 3 at the latest.
- Exception for commentary only: the event can be line 1 if the tension is inside the same line.

INVISIBLE STRUCTURE - enforced on every post:
- Never label paragraphs. No headers inside the post body.
- "Common mistake:" is banned even as an opener. Write it as a statement.
- Read the draft out loud. If it sounds like a report, rewrite it.

SELF-CHECK BEFORE RETURNING:
1. Does line 1 start with tension, not a source?
2. Are there any paragraph labels anywhere?
3. Does it read like a person talking or a structured explainer?
4. Would you stop scrolling for line 1?
If any answer is wrong, rewrite before returning.
""".strip()

TRUTH_AND_ORIGINALITY_APPENDIX = """
Truth contract:
- First-person perspective is allowed.
- First-person experiments, benchmarks, surveys, or measurements are only allowed when the truth profile permits them.
- If the evidence is external, interpret it honestly instead of impersonating it.
- If the evidence is mixed or weak, scope the claim instead of universalizing it.

Originality contract:
- Add a mechanism, contradiction, or applied systems lens.
- Do not merely summarize the source or clean up its wording.
- The finished draft should feel owned, not aggregated.
""".strip()


def _day_specific_generation_hints(contract: DayContract) -> list[str]:
    if contract.day == "Saturday":
        return [
            "Saturday tone hint: reflection should feel specific and lived-in, not preachy.",
            "Useful reflection phrasing includes 'I used to think...', 'I've started...', 'I now assume...', 'I no longer assume...', or 'That changed how I...'.",
        ]
    return []


def _load_voice_profile() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[2] / "config" / "voice_profile.json"
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return VOICE_PROFILE


_VOICE_PROFILE = _load_voice_profile()


def _compact_dossier(topic_context: TopicContext) -> dict[str, Any]:
    dossier = topic_context.dossier
    return {
        "topic_title": dossier.topic_title,
        "source_count": dossier.source_count,
        "consensus_summary": dossier.consensus_summary,
        "claim_summaries": dossier.claim_summaries[:3],
        "disagreement_notes": dossier.disagreement_notes[:2],
        "stronger_source_present": dossier.stronger_source_present,
        "weak_signal_echo": dossier.weak_signal_echo,
        "matched_run_note": dossier.matched_run_note,
        "sources": [
            {
                "source": source.reference.source,
                "title": source.reference.title,
                "source_quality": source.source_quality,
                "claim": source.claim,
                "confidence": source.confidence,
            }
            for source in dossier.sources[:3]
        ],
    }


def _compact_truth_profile(topic_context: TopicContext) -> dict[str, Any]:
    truth = topic_context.truth_profile
    return {
        "authority_mode": truth.authority_mode,
        "source_ownership": truth.source_ownership,
        "evidence_strength": truth.evidence_strength,
        "risk_level": truth.risk_level,
        "conflict_level": truth.conflict_level,
        "allowed_claim_posture": truth.allowed_claim_posture,
        "provenance_rule": truth.provenance_rule,
        "required_copy_moves": truth.required_copy_moves[:3],
        "forbidden_moves": truth.forbidden_moves[:3],
        "allows_first_person_experiment": truth.allows_first_person_experiment,
        "allows_exact_metrics": truth.allows_exact_metrics,
    }


def _compact_topic_context(topic_context: TopicContext) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": topic_context.candidate.title,
        "score_total": topic_context.candidate.score_total,
        "creator_post_type": topic_context.creator_post_type,
        "topic_pillar": topic_context.topic_pillar,
        "content_format": topic_context.content_format,
        "day_tone_hint": topic_context.day_tone_hint,
        "dossier": _compact_dossier(topic_context),
        "truth_profile": _compact_truth_profile(topic_context),
    }
    if topic_context.comment_insight is not None and topic_context.comment_usage_mode != "ignore":
        payload["comment_signal"] = {
            "source": topic_context.comment_insight.source,
            "signal_strength": topic_context.comment_insight.signal_strength,
            "top_sentiment": topic_context.comment_insight.top_sentiment,
            "usage_mode": topic_context.comment_usage_mode,
            "key_debates": topic_context.comment_insight.key_debates[:2],
            "strongest_pushback": topic_context.comment_insight.strongest_pushback,
            "common_question": topic_context.comment_insight.common_question,
        }
    return payload


def _compact_reference_contexts(reference_contexts: list[TopicContext]) -> list[dict[str, Any]]:
    return [
        {
            "title": context.candidate.title,
            "topic_pillar": context.topic_pillar,
            "creator_post_type": context.creator_post_type,
            "consensus_summary": context.dossier.consensus_summary,
            "allowed_claim_posture": context.truth_profile.allowed_claim_posture,
        }
        for context in reference_contexts[:2]
    ]


def _compact_generated_content(generated_content: GeneratedContent) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "primary": {
            "hook": generated_content.primary.hook,
            "draft_post": generated_content.primary.draft_post,
            "core_idea": generated_content.primary.core_idea[:5],
            "length_mode": generated_content.primary.length_mode,
        },
        "backups": [
            {
                "title": backup.title,
                "hook": backup.hook,
                "angle": backup.angle,
            }
            for backup in generated_content.backups[:2]
        ],
    }
    if generated_content.backup_text_post is not None:
        payload["backup_text_post"] = {
            "hook": generated_content.backup_text_post.hook,
            "draft_post": generated_content.backup_text_post.draft_post,
        }
    if generated_content.format_plan is not None:
        payload["format_plan"] = {
            "format": generated_content.format_plan.format,
            "what_to_create": generated_content.format_plan.what_to_create,
            "why_this_format": generated_content.format_plan.why_this_format,
            "asset_brief": generated_content.format_plan.asset_brief[:3],
        }
    return payload


def build_system_prompt(
    post_type: str,
    day_name: str = "",
    truth_profile: dict[str, Any] | None = None,
    *,
    content_format: str = "text",
) -> str:
    profile = _VOICE_PROFILE
    type_note = str(profile.get("post_type_notes", {}).get(post_type, "")).strip()
    template = get_template(post_type)
    format_instruction = get_format_instruction(content_format)
    day_hint = get_day_tone_hint(day_name) if day_name else ""
    evidence_policy = get_evidence_policy(post_type)
    banned_words = ", ".join(profile.get("banned_words", []))
    hook_patterns = "\n".join(f"- {pattern}" for pattern in profile.get("hook_patterns", []))
    hook_bans = "\n".join(f"- {pattern}" for pattern in profile.get("hook_bans", []))
    format_bans = "\n".join(f"- {pattern}" for pattern in profile.get("format_bans", []))
    base_rules = "\n".join(f"- {rule}" for rule in profile.get("base_rules", []))

    sections = [
        BASE_VOICE_PROMPT,
        TRUTH_AND_ORIGINALITY_APPENDIX,
    ]
    if base_rules:
        sections.append(f"VOICE RULES\n{base_rules}")
    if banned_words:
        sections.append(f"NEVER USE THESE CORPORATE WORDS\n{banned_words}")
    if hook_patterns:
        sections.append(f"HOOK PATTERNS\n{hook_patterns}")
    if hook_bans:
        sections.append(f"HOOK DISCIPLINE\n{hook_bans}")
    if format_bans:
        sections.append(f"INVISIBLE STRUCTURE\n{format_bans}")
    if type_note:
        sections.append(f"POST TYPE: {post_type.upper()}\n{type_note}")
    sections.append(f"CONTENT FORMAT: {content_format.upper()}")
    if template:
        sections.append(f"TEMPLATE FOR THIS POST TYPE\n{template}")
    if format_instruction:
        sections.append(f"FORMAT INSTRUCTIONS\n{format_instruction}")
    sections.append(
        "LENGTH GUIDANCE\n"
        "- There is no hard word-count target for this post.\n"
        "- Let the idea breathe when it needs space.\n"
        "- Stay readable, specific, and sharp. Depth is welcome; padding is not.\n"
        "- Use `length_mode` as a descriptive label only: choose `standard` for a tighter post and `extended` when the idea genuinely needs more room.\n"
        "- `length_mode_reason` is optional. Use it only if a longer draft is important to the point."
    )
    if day_hint:
        sections.append(f"TODAY'S TONE HINT\n{day_hint}")
    sections.append(
        "EVIDENCE POLICY\n"
        f"- Requires source: {evidence_policy['requires_source']}\n"
        f"- Requires distinct take: {evidence_policy['requires_distinct_take']}\n"
        f"- Requires explicit source mention in copy: {evidence_policy['requires_source_reference_in_copy']}"
    )
    if truth_profile is not None:
        sections.append(
            "TRUTH PROFILE\n"
            f"- Authority mode: {truth_profile.get('authority_mode', '')}\n"
            f"- Source ownership: {truth_profile.get('source_ownership', '')}\n"
            f"- Allowed claim posture: {truth_profile.get('allowed_claim_posture', '')}\n"
            f"- Provenance rule: {truth_profile.get('provenance_rule', '')}"
        )
    return "\n\n".join(section for section in sections if section).strip()


def normalize_originality_score(score: float) -> float:
    if 0.0 <= score <= 1.0:
        return round(score * 10.0, 2)
    return round(score, 2)


class ContentModel(Protocol):
    def choose_topic(self, contract: DayContract, topic_contexts: list[TopicContext], topic_override: str | None = None) -> TopicSelection:
        raise NotImplementedError


def _comment_prompt_block(topic_context: TopicContext) -> str:
    insight = topic_context.comment_insight
    usage_mode = topic_context.comment_usage_mode
    if insight is None or usage_mode == "ignore":
        return ""

    debates = "\n".join(f"- {item}" for item in insight.key_debates[:3]) or "- No clear debate extracted."
    header = (
        "COMMENT INSIGHT\n"
        f"- Source: {insight.source}\n"
        f"- Comment count: {insight.comment_count}\n"
        f"- Sentiment: {insight.top_sentiment}\n"
        f"- Signal strength: {insight.signal_strength}\n"
        f"- Strongest pushback: {insight.strongest_pushback or 'None captured.'}\n"
        f"- Common question: {insight.common_question or 'None captured.'}\n"
        "Key debates:\n"
        f"{debates}"
    )

    instructions = {
        "angle_driver": (
            "Use the comment tension as the angle driver for the post. The headline is context, not the hook.\n"
            "Do not mention Reddit, Hacker News, commenters, or a thread directly. Write the tension as your own informed perspective."
        ),
        "nuance_layer": (
            "Keep your own perspective as the main angle. Use the strongest pushback to add nuance or an honest caveat.\n"
            "Do not mention Reddit, Hacker News, commenters, or a thread directly."
        ),
        "example_source": (
            "Use the common question or confusion to frame what the post teaches.\n"
            "Do not mention Reddit, Hacker News, commenters, or a thread directly."
        ),
        "tone_signal": (
            "Use the comment sentiment only to calibrate how recognizable and grounded the situation feels.\n"
            "Do not mention Reddit, Hacker News, commenters, or a thread directly."
        ),
    }
    return "\n\n".join([header, instructions.get(usage_mode, "")]).strip()

    def generate_content(
        self,
        *,
        contract: DayContract,
        selection: TopicSelection,
        topic_context: TopicContext,
        reference_contexts: list[TopicContext],
        creator_context: str,
        revision_feedback: str | None = None,
    ) -> GeneratedContent:
        raise NotImplementedError

    def audit_content(
        self,
        *,
        audit_payload: dict[str, Any],
    ) -> ModelAuditResult:
        raise NotImplementedError

    def assess_originality(
        self,
        *,
        contract: DayContract,
        selection: TopicSelection,
        topic_context: TopicContext,
        generated_content: GeneratedContent,
    ) -> OriginalityAudit:
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
        stage_name: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        client = self._get_client().with_options(timeout=timeout_seconds, max_retries=0)
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
            raise RuntimeError(f"OpenAI {stage_name} response did not contain output text.")
        return json.loads(output_text)

    def choose_topic(self, contract: DayContract, topic_contexts: list[TopicContext], topic_override: str | None = None) -> TopicSelection:
        if topic_override:
            backups = [context.candidate.title for context in topic_contexts if context.candidate.title != topic_override][:2]
            return TopicSelection(
                selected_title=topic_override.strip(),
                selected_reason="Manual topic override supplied by the operator.",
                backup_titles=backups,
                caution_notes=[],
            )
        if not topic_contexts:
            raise RuntimeError("No candidates available for topic selection.")

        prompt = "\n".join(
            [
                f"Today is {contract.day}. Legacy weekday label: {contract.post_type}.",
                f"Creator post type for this run: {topic_contexts[0].creator_post_type}",
                f"Tone hint: {topic_contexts[0].day_tone_hint}",
                f"Description: {contract.description}",
                f"Legacy requirements: {', '.join(contract.requirements)}",
                "",
                "Select the strongest topic for a creator-first post and nominate two backups.",
                "Prefer topics with a sharp angle, defensible evidence, useful disagreement, and room for a real take.",
                "Do not prefer a topic just because the headline sounds dramatic or benchmark-heavy.",
                "",
                json.dumps([_compact_topic_context(context) for context in topic_contexts[:6]], indent=2),
            ]
        )
        try:
            payload = self._structured_call(
                schema_name="topic_selection",
                schema=TOPIC_SELECTION_SCHEMA,
                system_prompt=build_system_prompt(
                    topic_contexts[0].creator_post_type,
                    contract.day,
                    content_format=topic_contexts[0].content_format,
                ),
                user_prompt=prompt,
                reasoning_effort=self.config.selection_reasoning,
                stage_name="selection",
                timeout_seconds=self.config.selection_timeout_seconds,
            )
            return TopicSelection(**payload)
        except Exception:
            return TopicSelection(
                selected_title=topic_contexts[0].candidate.title,
                selected_reason="Fell back to the highest-scoring deterministic candidate.",
                backup_titles=[context.candidate.title for context in topic_contexts[1:3]],
                caution_notes=["Topic selection model call failed; deterministic fallback used."],
            )

    def generate_content(
        self,
        *,
        contract: DayContract,
        selection: TopicSelection,
        topic_context: TopicContext,
        reference_contexts: list[TopicContext],
        creator_context: str,
        revision_feedback: str | None = None,
    ) -> GeneratedContent:
        system_prompt = build_system_prompt(
            post_type=topic_context.creator_post_type,
            day_name=contract.day,
            truth_profile=asdict(topic_context.truth_profile),
            content_format=topic_context.content_format,
        )
        prompt_parts = [
            creator_context,
            f"Today is {contract.day}. Legacy weekday label: {contract.post_type}.",
            f"Creator post type: {topic_context.creator_post_type}.",
            f"Content format: {topic_context.content_format}.",
            f"Tone hint: {topic_context.day_tone_hint}",
            f"Contract description: {contract.description}",
            f"Legacy weekday requirements (soft bias, not the whole post): {', '.join(contract.requirements)}",
            "",
            f"Selected topic: {selection.selected_title}",
            f"Why selected: {selection.selected_reason}",
            f"Topic pillar: {topic_context.topic_pillar or 'unclassified'}",
            "",
            "Selected topic dossier:",
            json.dumps(_compact_dossier(topic_context), indent=2),
            "",
            "Truth profile:",
            json.dumps(_compact_truth_profile(topic_context), indent=2),
            "",
            "Reference topic contexts:",
            json.dumps(_compact_reference_contexts(reference_contexts), indent=2),
            "",
            "Return one primary post package and exactly two backup ideas.",
            f"Return `content_format` as '{topic_context.content_format}'.",
            "The primary core_idea array must contain 3 to 5 bullets only. Four is ideal. Never return 6 bullets.",
            "The primary post must use the exact output structure. It must not sound motivational, journalistic, or generic.",
            f"The primary post_type must be '{topic_context.creator_post_type}'.",
            "The primary post is always the public-facing caption or main text for the selected format.",
            "For non-text formats, `format_plan` is required and `backup_text_post` is required as a full plain-text fallback.",
            "For text format, both `format_plan` and `backup_text_post` must be null.",
            "The primary post and the backup_text_post must each satisfy the length policy independently.",
            "If the post type is short-form, stay comfortably below the word cap instead of writing to the exact limit.",
            f"Authority mode for this post: {topic_context.truth_profile.authority_mode}.",
            f"Allowed claim posture: {topic_context.truth_profile.allowed_claim_posture}",
            f"Provenance rule: {topic_context.truth_profile.provenance_rule}",
            "Do not reuse the same headline framing as the source signal.",
            "Do not restate the source conclusion directly.",
            "You must add a deeper mechanism, contradiction, or applied system explanation that makes the idea feel owned rather than aggregated.",
            "Never present an external experiment as if the creator ran it.",
            "If explicit provenance is required, make that clear in the hook or first two lines.",
            "If comment insight is provided, let it sharpen the angle silently. Do not write like a forum recap.",
            "Image suggestions should feel native to the chosen format.",
            *_day_specific_generation_hints(contract),
        ]
        comment_block = _comment_prompt_block(topic_context)
        if comment_block:
            prompt_parts.extend(["", comment_block])
        if revision_feedback:
            prompt_parts.extend(
                [
                    "",
                    "This is a forced reframing pass.",
                    "Revision feedback from the critic:",
                    revision_feedback,
                ]
            )

        payload = self._structured_call(
            schema_name="generation_payload",
            schema=GENERATION_PAYLOAD_SCHEMA,
            system_prompt=system_prompt,
            user_prompt="\n".join(prompt_parts),
            reasoning_effort=self.config.generation_reasoning,
            stage_name="generation",
            timeout_seconds=self.config.generation_timeout_seconds,
        )
        if payload["content_format"] != topic_context.content_format:
            raise RuntimeError(
                f"Model returned content_format '{payload['content_format']}' but '{topic_context.content_format}' was required."
            )
        primary_payload = payload["primary"]
        primary = self._post_package_from_payload(primary_payload)
        backups = [
            BackupIdea(
                title=backup["title"],
                angle=backup["angle"],
                hook=backup["hook"],
                why_now=backup["why_now"],
                visual_suggestion=backup["visual_suggestion"],
                image_suggestion=ImageSuggestion(**backup["image_suggestion"]) if backup.get("image_suggestion") else None,
            )
            for backup in payload["backups"]
        ]
        format_plan = self._format_plan_from_payload(payload.get("format_plan"))
        backup_text_post = self._post_package_from_payload(payload["backup_text_post"]) if payload.get("backup_text_post") else None
        return GeneratedContent(
            primary=primary,
            backups=backups,
            selected_topic_reason=payload["selected_topic_reason"],
            topic_dossier=topic_context.dossier,
            truth_profile=topic_context.truth_profile,
            format_plan=format_plan,
            backup_text_post=backup_text_post,
        )

    def assess_originality(
        self,
        *,
        contract: DayContract,
        selection: TopicSelection,
        topic_context: TopicContext,
        generated_content: GeneratedContent,
    ) -> OriginalityAudit:
        prompt = "\n".join(
            [
                f"Assess originality for this {contract.day} / {topic_context.creator_post_type} LinkedIn draft.",
                "External signals are valid inputs, but the draft must not reuse the same headline framing or restate the same conclusion directly.",
                "Single-source topics are allowed only if the draft introduces a deeper mechanism, contradiction, or applied system lens.",
                "Approve only if the draft feels owned and the originality score clears the required threshold for the post type.",
                "Return originality_score on a 0 to 10 scale. Do not use a 0 to 1 scale.",
                "",
                f"Selected topic: {selection.selected_title}",
                f"Selection reason: {selection.selected_reason}",
                "",
                "Topic context and source evidence:",
                json.dumps(_compact_topic_context(topic_context), indent=2),
                "",
                "Generated draft:",
                json.dumps(_compact_generated_content(generated_content), indent=2),
            ]
        )
        payload = self._structured_call(
            schema_name="originality_audit",
            schema=ORIGINALITY_AUDIT_SCHEMA,
            system_prompt=build_system_prompt(
                topic_context.creator_post_type,
                contract.day,
                asdict(topic_context.truth_profile),
                content_format=topic_context.content_format,
            ),
            user_prompt=prompt,
            reasoning_effort=self.config.audit_reasoning,
            stage_name="originality",
            timeout_seconds=self.config.originality_timeout_seconds,
        )
        payload["originality_score"] = normalize_originality_score(float(payload["originality_score"]))
        return OriginalityAudit(**payload)

    def audit_content(
        self,
        *,
        audit_payload: dict[str, Any],
    ) -> ModelAuditResult:
        prompt = "\n".join(
            [
                f"Audit this {audit_payload['day_name']} / {audit_payload['creator_post_type']} content package.",
                "Fail it if it sounds generic, beginner-level, or AI-obvious.",
                "Fail it if it does not genuinely satisfy the creator post type and truth posture.",
                "Fail it if it violates the assigned authority mode, provenance rule, or claim posture.",
                "",
                "Compact audit payload:",
                json.dumps(audit_payload, indent=2),
            ]
        )
        payload = self._structured_call(
            schema_name="audit_result",
            schema=AUDIT_RESULT_SCHEMA,
            system_prompt=build_system_prompt(
                audit_payload["creator_post_type"],
                audit_payload["day_name"],
                {
                    "authority_mode": audit_payload["truth_posture"]["authority_mode"],
                    "source_ownership": audit_payload["truth_posture"]["source_ownership"],
                    "evidence_strength": audit_payload["truth_posture"]["evidence_strength"],
                    "allowed_claim_posture": audit_payload["truth_posture"]["allowed_claim_posture"],
                    "provenance_rule": audit_payload["truth_posture"]["provenance_rule"],
                },
                content_format=audit_payload["content_format"],
            ),
            user_prompt=prompt,
            reasoning_effort=self.config.audit_reasoning,
            stage_name="audit",
            timeout_seconds=self.config.audit_timeout_seconds,
        )
        return ModelAuditResult(**payload)

    def _post_package_from_payload(self, payload: dict[str, Any]) -> PostPackage:
        return PostPackage(
            day=payload["day"],
            post_type=payload["post_type"],
            hook=payload["hook"],
            core_idea=list(payload["core_idea"]),
            draft_post=payload["draft_post"],
            visual_suggestion=payload["visual_suggestion"],
            why_this_works=payload["why_this_works"],
            source_refs=[SourceReference(**item) for item in payload["source_refs"]],
            self_audit=SelfAudit(**payload["self_audit"]),
            image_suggestion=ImageSuggestion(**payload["image_suggestion"]) if payload.get("image_suggestion") else None,
            length_mode=payload.get("length_mode", "standard"),
            length_mode_reason=payload.get("length_mode_reason"),
        )

    def _format_plan_from_payload(self, payload: dict[str, Any] | None) -> FormatPlan | None:
        if not payload:
            return None
        slides_payload = payload.get("slides")
        slides = [CarouselSlide(title=item["title"], bullets=list(item["bullets"])) for item in slides_payload] if slides_payload else None
        return FormatPlan(
            format=payload["format"],
            what_to_create=payload["what_to_create"],
            why_this_format=payload["why_this_format"],
            asset_brief=list(payload["asset_brief"]),
            deadline_hint=payload["deadline_hint"],
            caption_note=payload["caption_note"],
            visual_structure=payload.get("visual_structure"),
            slides=slides,
        )
