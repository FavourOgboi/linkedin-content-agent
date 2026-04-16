from __future__ import annotations

from linkedin_content_agent.models import EmailPayload, GeneratedContent, RunSummary


def render_markdown(summary: RunSummary, generated_content: GeneratedContent, review_url: str | None = None) -> str:
    backup_lines = []
    for backup in generated_content.backups:
        backup_lines.append(f"## Backup Idea: {backup.title}")
        backup_lines.append(f"- Angle: {backup.angle}")
        backup_lines.append(f"- Hook: {backup.hook}")
        backup_lines.append(f"- Why now: {backup.why_now}")
        backup_lines.append(f"- Visual: {backup.visual_suggestion}")
        backup_lines.append("")

    source_lines = [
        f"- {reference.source}: [{reference.title}]({reference.url})"
        for reference in generated_content.primary.source_refs
    ]
    review_line = (
        f"Review URL: {review_url}"
        if review_url
        else f"Review locally: python -m linkedin_content_agent.cli review --run-id {summary.run_id} --decision approved --notes \"Your notes\""
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

    sections = [
        f"# {summary.day} - {summary.post_type}",
        "",
        f"- Run ID: `{summary.run_id}`",
        f"- Status: `{summary.status}`",
        f"- Selected topic: {summary.selected_topic}",
        review_line,
        "",
        "## Hook",
        generated_content.primary.hook,
        "",
        "## Core Idea",
        *[f"- {bullet}" for bullet in generated_content.primary.core_idea],
        "",
        "## Draft Post",
        generated_content.primary.draft_post,
        "",
        "## Visual Suggestion",
        generated_content.primary.visual_suggestion,
        "",
        "## Why This Works",
        generated_content.primary.why_this_works,
        "",
        "## Sources",
        *source_lines,
        "",
        "## Self Audit",
        *[f"- Passed: {item}" for item in generated_content.primary.self_audit.passed_checks],
        *[f"- Note: {item}" for item in generated_content.primary.self_audit.critic_notes],
        "",
        *credibility_lines,
        *originality_lines,
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
        or f"Run locally: python -m linkedin_content_agent.cli review --run-id {summary.run_id} --decision approved --notes \"Your notes\""
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
            f"Run ID: {summary.run_id}",
            f"Day / Type: {summary.day} / {summary.post_type}",
            f"Selected topic: {summary.selected_topic}",
            f"Review: {review_block}",
            "",
            "HOOK",
            generated_content.primary.hook,
            "",
            "CORE IDEA",
            *[f"- {bullet}" for bullet in generated_content.primary.core_idea],
            "",
            "DRAFT POST",
            generated_content.primary.draft_post,
            "",
            "VISUAL",
            generated_content.primary.visual_suggestion,
            "",
            "WHY THIS WORKS",
            generated_content.primary.why_this_works,
            *credibility_block,
            *originality_block,
            "",
            "BACKUP IDEAS",
            backup_block or "No backup ideas generated.",
        ]
    )
    return EmailPayload(
        subject=f"[LinkedIn Content Agent] {summary.day} - {summary.selected_topic}",
        body_text=body,
        recipient=recipient,
    )
