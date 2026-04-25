from __future__ import annotations


DAY_ENUM = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
POST_TYPE_ENUM = [
    "insight",
    "relatable",
    "commentary",
    "teaching",
    "inspiration",
]
CONTENT_FORMAT_ENUM = ["text", "photo", "screenshot", "carousel", "infographic"]
LENGTH_MODE_ENUM = ["standard", "extended"]
TRANSFORMATION_TYPE_ENUM = ["reframed", "deepened", "challenged", "applied"]
ORIGINALITY_DECISION_ENUM = ["approve", "reject"]


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

IMAGE_SUGGESTION_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "type": {"type": "string"},
        "description": {"type": "string"},
        "how_to_create": {"type": "string"},
        "why_it_works": {"type": "string"},
    },
    "required": ["type", "description", "how_to_create", "why_it_works"],
    "additionalProperties": False,
}

CAROUSEL_SLIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "bullets"],
    "additionalProperties": False,
}

FORMAT_PLAN_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "format": {"type": "string", "enum": CONTENT_FORMAT_ENUM},
        "what_to_create": {"type": "string"},
        "why_this_format": {"type": "string"},
        "asset_brief": {"type": "array", "items": {"type": "string"}},
        "deadline_hint": {"type": "string"},
        "caption_note": {"type": "string"},
        "visual_structure": {"type": ["string", "null"]},
        "slides": {"type": ["array", "null"], "items": CAROUSEL_SLIDE_SCHEMA},
    },
    "required": [
        "format",
        "what_to_create",
        "why_this_format",
        "asset_brief",
        "deadline_hint",
        "caption_note",
        "visual_structure",
        "slides",
    ],
    "additionalProperties": False,
}

POST_PACKAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "day": {"type": "string", "enum": DAY_ENUM},
        "post_type": {"type": "string", "enum": POST_TYPE_ENUM},
        "hook": {"type": "string"},
        "core_idea": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5},
        "draft_post": {"type": "string"},
        "visual_suggestion": {"type": "string"},
        "image_suggestion": IMAGE_SUGGESTION_SCHEMA,
        "why_this_works": {"type": "string"},
        "source_refs": {"type": "array", "items": SOURCE_REFERENCE_SCHEMA, "minItems": 1},
        "self_audit": SELF_AUDIT_SCHEMA,
        "length_mode": {"type": "string", "enum": LENGTH_MODE_ENUM},
        "length_mode_reason": {"type": ["string", "null"]},
    },
    "required": [
        "day",
        "post_type",
        "hook",
        "core_idea",
        "draft_post",
        "visual_suggestion",
        "image_suggestion",
        "why_this_works",
        "source_refs",
        "self_audit",
        "length_mode",
        "length_mode_reason",
    ],
    "additionalProperties": False,
}

NULLABLE_POST_PACKAGE_SCHEMA = {
    "type": ["object", "null"],
    "properties": POST_PACKAGE_SCHEMA["properties"],
    "required": POST_PACKAGE_SCHEMA["required"],
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
        "image_suggestion": IMAGE_SUGGESTION_SCHEMA,
    },
    "required": ["title", "angle", "hook", "why_now", "visual_suggestion", "image_suggestion"],
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
        "content_format": {"type": "string", "enum": CONTENT_FORMAT_ENUM},
        "primary": POST_PACKAGE_SCHEMA,
        "backups": {"type": "array", "items": BACKUP_IDEA_SCHEMA, "minItems": 2, "maxItems": 2},
        "selected_topic_reason": {"type": "string"},
        "format_plan": FORMAT_PLAN_SCHEMA,
        "backup_text_post": NULLABLE_POST_PACKAGE_SCHEMA,
    },
    "required": ["content_format", "primary", "backups", "selected_topic_reason", "format_plan", "backup_text_post"],
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

ORIGINALITY_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "source_signal": {"type": "string"},
        "core_claim_from_source": {"type": "string"},
        "transformation_type": {"type": "string", "enum": TRANSFORMATION_TYPE_ENUM},
        "new_mechanism_or_insight": {"type": "string"},
        "originality_score": {"type": "number"},
        "decision": {"type": "string", "enum": ORIGINALITY_DECISION_ENUM},
    },
    "required": [
        "source_signal",
        "core_claim_from_source",
        "transformation_type",
        "new_mechanism_or_insight",
        "originality_score",
        "decision",
    ],
    "additionalProperties": False,
}
