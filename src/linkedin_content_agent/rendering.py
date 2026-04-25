from __future__ import annotations

from dataclasses import asdict

from linkedin_content_agent.content_strategy import comment_usage_affects_subject
from linkedin_content_agent.models import EmailPayload, GeneratedContent, RunSummary


def render_image_suggestion(image_suggestion: dict | None, fallback: str = "") -> str:
    if not image_suggestion:
        return f"Visual: {fallback}" if fallback else ""

    return (
        f"Image suggestion ({image_suggestion.get('type', 'unknown')}): "
        f"{image_suggestion.get('description', '')} - "
        f"{image_suggestion.get('how_to_create', '')} - "
        f"Why it works: {image_suggestion.get('why_it_works', '')}"
    ).strip()


def render_format_plan(generated_content: GeneratedContent) -> list[str]:
    if generated_content.format_plan is None:
        return []

    plan = generated_content.format_plan
    lines = [
        "## Format Plan",
        f"- Format: {plan.format}",
        f"- What to create: {plan.what_to_create}",
        f"- Why this format: {plan.why_this_format}",
        f"- Deadline: {plan.deadline_hint}",
        f"- Caption note: {plan.caption_note}",
    ]
    if plan.visual_structure:
        lines.append(f"- Visual structure: {plan.visual_structure}")
    for item in plan.asset_brief:
        lines.append(f"- Asset brief: {item}")
    if plan.slides:
        lines.append("")
        lines.append("### Slides")
        for index, slide in enumerate(plan.slides, start=1):
            lines.append(f"- Slide {index}: {slide.title}")
            for bullet in slide.bullets:
                lines.append(f"  - {bullet}")
    lines.append("")
    return lines


def render_post_package(post, *, title: str) -> list[str]:
    return [
        f"## {title}",
        "### Hook",
        post.hook,
        "",
        "### Core Idea",
        *[f"- {bullet}" for bullet in post.core_idea],
        "",
        "### Draft Post",
        post.draft_post,
        "",
        "### Visual Suggestion",
        render_image_suggestion(
            asdict(post.image_suggestion) if post.image_suggestion is not None else None,
            fallback=post.visual_suggestion,
        ),
        "",
        "### Why This Works",
        post.why_this_works,
        "",
    ]


def _comment_usage_explanation(usage_mode: str) -> str:
    return {
        "angle_driver": "Community tension drove the hook and main argument.",
        "nuance_layer": "Community pushback sharpened the nuance or caveat in the post.",
        "example_source": "The most common question in the comments framed what the post teaches.",
        "tone_signal": "Comment sentiment was used only to calibrate whether the situation felt broadly recognizable.",
        "ignore": "Comment insight was collected but not used in the public-facing copy.",
    }.get(usage_mode, "Comment usage was not classified.")


def render_comment_insight_lines(generated_content: GeneratedContent) -> list[str]:
    insight = generated_content.comment_insight
    if insight is None:
        return []
    lines = [
        "## Comment Insight",
        f"- Source: {insight.source}",
        f"- Comment count: {insight.comment_count}",
        f"- Sentiment: {insight.top_sentiment}",
        f"- Signal strength: {insight.signal_strength}",
        f"- Usage mode: {generated_content.comment_usage_mode}",
        *[f"- Key debate: {item}" for item in insight.key_debates],
        f"- Strongest pushback: {insight.strongest_pushback or 'None captured.'}",
        f"- Common question: {insight.common_question or 'None captured.'}",
        f"- How this shaped the post: {_comment_usage_explanation(generated_content.comment_usage_mode)}",
        "",
    ]
    return lines


def render_markdown(summary: RunSummary, generated_content: GeneratedContent, review_url: str | None = None) -> str:
    backup_lines = []
    for backup in generated_content.backups:
        backup_lines.append(f"## Backup Idea: {backup.title}")
        backup_lines.append(f"- Angle: {backup.angle}")
        backup_lines.append(f"- Hook: {backup.hook}")
        backup_lines.append(f"- Why now: {backup.why_now}")
        image_line = render_image_suggestion(
            asdict(backup.image_suggestion) if backup.image_suggestion is not None else None,
            fallback=backup.visual_suggestion,
        )
        if image_line:
            backup_lines.append(f"- {image_line}")
        backup_lines.append("")

    source_lines = [
        f"- {reference.source}: [{reference.title}]({reference.url})"
        for reference in generated_content.primary.source_refs
    ]
    review_line = (
        f"Review URL: {review_url}"
        if review_url
        else (
            f"Review locally: python -m linkedin_content_agent.cli review --run-id {summary.run_id} "
            '--decision approved --notes "Your notes"'
        )
    )
    originality_lines: list[str] = []
    if generated_content.originality_audit is not None:
        originality_lines = [
            "## Originality Review",
            f"- Source signal: {generated_content.originality_audit.source_signal}",
            f"- Source claim: {generated_content.originality_audit.core_claim_from_source}",
            f"- Transformation: {generated_content.originality_audit.transformation_type}",
            f"- New insight: {generated_content.originality_audit.new_mechanism_or_insight}",
            f"- Originality score: {generated_content.originality_audit.originality_score}",
            f"- Decision: {generated_content.originality_audit.decision}",
            "",
        ]
    credibility_lines: list[str] = []
    if generated_content.truth_profile is not None and generated_content.topic_dossier is not None:
        credibility_lines = [
            "## Credibility Review",
            f"- Authority mode: {generated_content.truth_profile.authority_mode}",
            f"- Source ownership: {generated_content.truth_profile.source_ownership}",
            f"- Evidence strength: {generated_content.truth_profile.evidence_strength}",
            f"- Risk level: {generated_content.truth_profile.risk_level}",
            f"- Conflict level: {generated_content.truth_profile.conflict_level}",
            f"- Allowed posture: {generated_content.truth_profile.allowed_claim_posture}",
            f"- Provenance rule: {generated_content.truth_profile.provenance_rule}",
            f"- Dossier summary: {generated_content.topic_dossier.consensus_summary}",
            *[f"- Dossier note: {note}" for note in generated_content.topic_dossier.disagreement_notes],
            *[f"- Claim summary: {item}" for item in generated_content.topic_dossier.claim_summaries],
            "",
        ]
    backup_text_lines = (
        render_post_package(generated_content.backup_text_post, title="Backup Text Post")
        if generated_content.backup_text_post is not None
        else []
    )

    sections = [
        f"# {summary.day} - {summary.creator_post_type or summary.post_type} - {summary.content_format.upper()}",
        "",
        *(
            [
                "## Audit Warning",
                f"- Audit skipped: {summary.audit_skipped}",
                f"- Reason: {summary.audit_skip_reason or 'Audit was unavailable.'}",
                "",
            ]
            if summary.audit_skipped
            else []
        ),
        f"- Run ID: `{summary.run_id}`",
        f"- Status: `{summary.status}`",
        f"- Creator post type: {summary.creator_post_type or generated_content.primary.post_type}",
        f"- Content format: {summary.content_format}",
        f"- Topic pillar: {summary.topic_pillar or 'unclassified'}",
        f"- Legacy weekday type: {summary.post_type}",
        f"- Selected topic: {summary.selected_topic}",
        review_line,
        "",
        *render_format_plan(generated_content),
        *render_post_package(generated_content.primary, title="Primary Post"),
        "## Sources",
        *source_lines,
        "",
        "## Self Audit",
        *[f"- Passed: {item}" for item in generated_content.primary.self_audit.passed_checks],
        *[f"- Note: {item}" for item in generated_content.primary.self_audit.critic_notes],
        "",
        *credibility_lines,
        *render_comment_insight_lines(generated_content),
        *originality_lines,
        *backup_text_lines,
        *backup_lines,
    ]
    return "\n".join(sections).strip() + "\n"


def render_email_payload(
    summary: RunSummary,
    generated_content: GeneratedContent,
    recipient: str,
    *,
    review_url: str | None = None,
) -> EmailPayload:
    review_block = (
        review_url
        or (
            f"Run locally: python -m linkedin_content_agent.cli review --run-id {summary.run_id} "
            '--decision approved --notes "Your notes"'
        )
    )
    originality_block = []
    if generated_content.originality_audit is not None:
        originality_block = [
            "",
            "ORIGINALITY REVIEW",
            f"Source signal: {generated_content.originality_audit.source_signal}",
            f"Source claim: {generated_content.originality_audit.core_claim_from_source}",
            f"Transformation: {generated_content.originality_audit.transformation_type}",
            f"New insight: {generated_content.originality_audit.new_mechanism_or_insight}",
            f"Originality score: {generated_content.originality_audit.originality_score}",
            f"Decision: {generated_content.originality_audit.decision}",
        ]
    credibility_block = []
    if generated_content.truth_profile is not None and generated_content.topic_dossier is not None:
        credibility_block = [
            "",
            "CREDIBILITY REVIEW",
            f"Authority mode: {generated_content.truth_profile.authority_mode}",
            f"Source ownership: {generated_content.truth_profile.source_ownership}",
            f"Evidence strength: {generated_content.truth_profile.evidence_strength}",
            f"Risk level: {generated_content.truth_profile.risk_level}",
            f"Conflict level: {generated_content.truth_profile.conflict_level}",
            f"Allowed posture: {generated_content.truth_profile.allowed_claim_posture}",
            f"Provenance rule: {generated_content.truth_profile.provenance_rule}",
            f"Dossier summary: {generated_content.topic_dossier.consensus_summary}",
            *[f"Dossier note: {note}" for note in generated_content.topic_dossier.disagreement_notes],
        ]
    backup_block = "\n\n".join(
        [
            "\n".join(
                [
                    f"Backup: {backup.title}",
                    f"Angle: {backup.angle}",
                    f"Hook: {backup.hook}",
                    f"Why now: {backup.why_now}",
                    f"Visual: {backup.visual_suggestion}",
                ]
            )
            for backup in generated_content.backups
        ]
    )

    body = "\n".join(
        [
            *(
                [
                    "AUDIT WARNING",
                    summary.audit_skip_reason or "Audit was skipped. Review manually before posting.",
                    "",
                ]
                if summary.audit_skipped
                else []
            ),
            f"Run ID: {summary.run_id}",
            f"Day / Creator Type: {summary.day} / {summary.creator_post_type or generated_content.primary.post_type}",
            f"Content format: {summary.content_format}",
            f"Legacy weekday type: {summary.post_type}",
            f"Topic pillar: {summary.topic_pillar or 'unclassified'}",
            f"Selected topic: {summary.selected_topic}",
            f"Review: {review_block}",
            "",
            *(
                [
                    "FORMAT PLAN",
                    f"Format: {generated_content.format_plan.format}",
                    f"What to create: {generated_content.format_plan.what_to_create}",
                    f"Why this format: {generated_content.format_plan.why_this_format}",
                    *[f"Asset brief: {item}" for item in generated_content.format_plan.asset_brief],
                    *(
                        [f"Visual structure: {generated_content.format_plan.visual_structure}"]
                        if generated_content.format_plan.visual_structure
                        else []
                    ),
                    *(
                        [f"Slide {index}: {slide.title} | {'; '.join(slide.bullets)}" for index, slide in enumerate(generated_content.format_plan.slides, start=1)]
                        if generated_content.format_plan.slides
                        else []
                    ),
                    f"Deadline: {generated_content.format_plan.deadline_hint}",
                    f"Caption note: {generated_content.format_plan.caption_note}",
                    "",
                ]
                if generated_content.format_plan is not None
                else []
            ),
            "PRIMARY POST",
            f"Hook: {generated_content.primary.hook}",
            "Draft:",
            generated_content.primary.draft_post,
            f"Visual: {render_image_suggestion(asdict(generated_content.primary.image_suggestion) if generated_content.primary.image_suggestion is not None else None, fallback=generated_content.primary.visual_suggestion)}",
            f"Why this works: {generated_content.primary.why_this_works}",
            *(
                [
                    "",
                    "BACKUP TEXT POST",
                    f"Hook: {generated_content.backup_text_post.hook}",
                    "Draft:",
                    generated_content.backup_text_post.draft_post,
                    f"Visual: {render_image_suggestion(asdict(generated_content.backup_text_post.image_suggestion) if generated_content.backup_text_post.image_suggestion is not None else None, fallback=generated_content.backup_text_post.visual_suggestion)}",
                ]
                if generated_content.backup_text_post is not None
                else []
            ),
            *credibility_block,
            *(
                [
                    "",
                    "COMMENT INSIGHT",
                    f"Source: {generated_content.comment_insight.source}",
                    f"Comment count: {generated_content.comment_insight.comment_count}",
                    f"Sentiment: {generated_content.comment_insight.top_sentiment}",
                    f"Signal strength: {generated_content.comment_insight.signal_strength}",
                    f"Usage mode: {generated_content.comment_usage_mode}",
                    *[f"Key debate: {item}" for item in generated_content.comment_insight.key_debates],
                    f"Strongest pushback: {generated_content.comment_insight.strongest_pushback or 'None captured.'}",
                    f"Common question: {generated_content.comment_insight.common_question or 'None captured.'}",
                    f"How this shaped the post: {_comment_usage_explanation(generated_content.comment_usage_mode)}",
                ]
                if generated_content.comment_insight is not None
                else []
            ),
            *originality_block,
            "",
            "BACKUP IDEAS",
            backup_block or "No backup ideas generated.",
        ]
    )
    subject_suffix = " [+comments]" if comment_usage_affects_subject(generated_content.comment_usage_mode) else ""
    return EmailPayload(
        subject=f"[LinkedIn Content Agent] {summary.day} - {summary.creator_post_type or generated_content.primary.post_type} - {summary.content_format.upper()}{subject_suffix}",
        body_text=body,
        recipient=recipient,
    )
