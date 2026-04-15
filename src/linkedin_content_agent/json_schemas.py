from __future__ import annotations


DAY_ENUM = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
POST_TYPE_ENUM = [
    "Build / Experiment",
    "Micro-Teach",
    "Knowledge / Carousel",
    "AI / Industry Insight",
    "Thinking / Conviction",
    "Thinking / Reflection",
    "Build Story",
]


SOURCE_REFERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "title": {"type": "string"},
        "url": {"type": "string"},
    },
    "required": ["source", "title", "url"],
    "additionalProperties": False,
}

SELF_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "passed_checks": {"type": "array", "items": {"type": "string"}},
        "critic_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["passed_checks", "critic_notes"],
    "additionalProperties": False,
}

POST_PACKAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "day": {"type": "string", "enum": DAY_ENUM},
        "post_type": {"type": "string", "enum": POST_TYPE_ENUM},
        "hook": {"type": "string"},
        "core_idea": {"type": "array", "items": {"type": "string"}},
        "draft_post": {"type": "string"},
        "visual_suggestion": {"type": "string"},
        "why_this_works": {"type": "string"},
        "source_refs": {"type": "array", "items": SOURCE_REFERENCE_SCHEMA},
        "self_audit": SELF_AUDIT_SCHEMA,
    },
    "required": [
        "day",
        "post_type",
        "hook",
        "core_idea",
        "draft_post",
        "visual_suggestion",
        "why_this_works",
        "source_refs",
        "self_audit",
    ],
    "additionalProperties": False,
}

BACKUP_IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "angle": {"type": "string"},
        "hook": {"type": "string"},
        "why_now": {"type": "string"},
        "visual_suggestion": {"type": "string"},
    },
    "required": ["title", "angle", "hook", "why_now", "visual_suggestion"],
    "additionalProperties": False,
}

TOPIC_SELECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_title": {"type": "string"},
        "selected_reason": {"type": "string"},
        "backup_titles": {"type": "array", "items": {"type": "string"}},
        "caution_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["selected_title", "selected_reason", "backup_titles", "caution_notes"],
    "additionalProperties": False,
}

GENERATION_PAYLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "primary": POST_PACKAGE_SCHEMA,
        "backups": {"type": "array", "items": BACKUP_IDEA_SCHEMA},
        "selected_topic_reason": {"type": "string"},
    },
    "required": ["primary", "backups", "selected_topic_reason"],
    "additionalProperties": False,
}

AUDIT_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "revision_instructions": {"type": "string"},
    },
    "required": ["passed", "reasons", "revision_instructions"],
    "additionalProperties": False,
}
