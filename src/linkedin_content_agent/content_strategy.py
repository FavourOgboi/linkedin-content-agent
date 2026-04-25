from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import random
from typing import Any, Literal


CreatorPostType = Literal["insight", "relatable", "commentary", "teaching", "inspiration"]
TopicPillar = Literal["ai_ml", "data_engineering", "python_backend", "beginner_practice", "career_insight", ""]
ContentFormat = Literal["text", "photo", "screenshot", "carousel", "infographic"]
CommentUsageMode = Literal["angle_driver", "nuance_layer", "example_source", "tone_signal", "ignore"]

CREATOR_POST_TYPES: tuple[CreatorPostType, ...] = (
    "insight",
    "relatable",
    "commentary",
    "teaching",
    "inspiration",
)

CONTENT_FORMATS: tuple[ContentFormat, ...] = (
    "text",
    "photo",
    "screenshot",
    "carousel",
    "infographic",
)

LEGACY_POST_TYPE_MAP: dict[str, CreatorPostType] = {
    "build / experiment": "insight",
    "micro-teach": "teaching",
    "knowledge / carousel": "insight",
    "ai / industry insight": "commentary",
    "thinking / conviction": "insight",
    "thinking / reflection": "inspiration",
    "build story": "inspiration",
}

POST_TYPE_WEIGHTS: dict[str, dict[CreatorPostType, int]] = {
    "Monday": {"insight": 20, "relatable": 15, "commentary": 15, "teaching": 20, "inspiration": 30},
    "Tuesday": {"insight": 35, "relatable": 20, "commentary": 20, "teaching": 20, "inspiration": 5},
    "Wednesday": {"insight": 20, "relatable": 20, "commentary": 35, "teaching": 20, "inspiration": 5},
    "Thursday": {"insight": 20, "relatable": 20, "commentary": 20, "teaching": 35, "inspiration": 5},
    "Friday": {"insight": 20, "relatable": 35, "commentary": 20, "teaching": 15, "inspiration": 10},
    "Saturday": {"insight": 30, "relatable": 25, "commentary": 15, "teaching": 15, "inspiration": 15},
    "Sunday": {"insight": 25, "relatable": 20, "commentary": 15, "teaching": 10, "inspiration": 30},
}

DAY_ALLOWED_POST_TYPES: dict[str, tuple[CreatorPostType, ...]] = {
    "Monday": ("insight", "teaching", "inspiration"),
    "Tuesday": ("insight", "relatable", "teaching"),
    "Wednesday": ("insight", "relatable", "commentary", "teaching"),
    "Thursday": ("insight", "commentary", "teaching"),
    "Friday": ("insight", "relatable", "commentary"),
    "Saturday": ("insight", "relatable", "inspiration"),
    "Sunday": ("insight", "relatable", "inspiration"),
}

FORMAT_WEIGHTS_BY_DAY: dict[str, dict[ContentFormat, int]] = {
    "Monday": {"text": 40, "photo": 30, "screenshot": 10, "carousel": 5, "infographic": 15},
    "Tuesday": {"text": 20, "photo": 5, "screenshot": 20, "carousel": 40, "infographic": 15},
    "Wednesday": {"text": 45, "photo": 5, "screenshot": 15, "carousel": 20, "infographic": 15},
    "Thursday": {"text": 25, "photo": 5, "screenshot": 25, "carousel": 20, "infographic": 25},
    "Friday": {"text": 30, "photo": 15, "screenshot": 30, "carousel": 15, "infographic": 10},
    "Saturday": {"text": 20, "photo": 45, "screenshot": 10, "carousel": 10, "infographic": 15},
    "Sunday": {"text": 35, "photo": 35, "screenshot": 10, "carousel": 10, "infographic": 10},
}

DAY_TONE_HINTS = {
    "Monday": "Start the week with useful energy. Encourage momentum, but keep the value concrete.",
    "Tuesday": "Stay practical and narrow. Teach something small and genuinely helpful.",
    "Wednesday": "Midweek is a good moment for a sharp take or a pattern people keep missing.",
    "Thursday": "Lean toward explanation and interpretation. Show what changes in practice.",
    "Friday": "Use a little more edge or humor. It can be lighter, but it still needs a point.",
    "Saturday": "Reflect without becoming vague. Sound like someone thinking in public, not preaching.",
    "Sunday": "Be human and grounded. A calm, specific post works better than a grand statement.",
}

POST_TYPE_TEMPLATES = {
    "insight": "Hook\nObservation\nPattern or shift in thinking\nImplication or lesson",
    "relatable": "Scenario\nRecognition moment\nUnderlying truth\nOptional short takeaway",
    "commentary": "Hook\nWhat happened in one line\nYour take\nWhy it matters",
    "teaching": """\
Write this as flowing short paragraphs, not labeled sections.

Invisible structure to follow (do NOT label these in the post):
1. Open with the mistake or the gap, stated as a plain observation
2. Explain why people make that mistake in one sentence
3. Give the better mental model or approach in plain language
4. Use one concrete example, analogy, or code line only if it sharpens the point
5. Close with the practical implication and mention the source casually near the end

Rules:
- No paragraph headers. No 'Takeaway:' or 'Why this works:' or any label.
- One concept only. Narrow scope equals better post.
- Source or project reference goes near the close, one casual line only.
- If you feel like adding a bullet list, rewrite it as a sentence instead.
""",
    "inspiration": "Specific moment\nQuiet lesson\nShort close",
}

FORMAT_OUTPUT_SPEC: dict[ContentFormat, str] = {
    "text": """\
FORMAT OUTPUT: TEXT
- Generate a normal LinkedIn text post only.
- `format_plan` must be null.
- `backup_text_post` must be null.
""",
    "photo": """\
FORMAT OUTPUT: PHOTO
- Generate the main caption/post as `primary`.
- Generate a `format_plan` that tells the creator exactly what photo to take.
- The asset brief must specify what should be visible, what to avoid, and why the image fits the post.
- Generate a full `backup_text_post` in case the creator does not want to take the photo today.
""",
    "screenshot": """\
FORMAT OUTPUT: SCREENSHOT
- Generate the main caption/post as `primary`.
- Generate a `format_plan` that says exactly what to screenshot, what to crop, and what to hide.
- The screenshot must feel like the point, not decoration.
- Generate a full `backup_text_post` in case the creator does not want to capture the screenshot today.
""",
    "carousel": """\
FORMAT OUTPUT: CAROUSEL
- Generate the posting caption as `primary`.
- Generate a `format_plan` with slide-by-slide outline in `slides`.
- Each slide needs a short title and tight bullets that can be read quickly.
- Generate a full `backup_text_post` in case the creator does not want to build the carousel today.
""",
    "infographic": """\
FORMAT OUTPUT: INFOGRAPHIC
- Generate the posting caption as `primary`.
- Generate a `format_plan` with a clear visual structure and a concrete asset brief.
- The infographic should explain one concept visually, not become a dense poster.
- Generate a full `backup_text_post` in case the creator does not want to design the infographic today.
""",
}

EVIDENCE_POLICIES: dict[CreatorPostType, dict[str, Any]] = {
    "insight": {
        "requires_source": False,
        "requires_distinct_take": True,
        "requires_source_reference_in_copy": False,
    },
    "relatable": {
        "requires_source": False,
        "requires_distinct_take": False,
        "requires_source_reference_in_copy": False,
    },
    "commentary": {
        "requires_source": True,
        "requires_distinct_take": True,
        "requires_source_reference_in_copy": True,
    },
    "teaching": {
        "requires_source": False,
        "requires_distinct_take": False,
        "requires_source_reference_in_copy": False,
    },
    "inspiration": {
        "requires_source": False,
        "requires_distinct_take": False,
        "requires_source_reference_in_copy": False,
    },
}

ORIGINALITY_THRESHOLDS: dict[CreatorPostType, float] = {
    "insight": 7.2,
    "relatable": 6.0,
    "commentary": 7.3,
    "teaching": 6.7,
    "inspiration": 6.2,
}

COMMENT_INSIGHT_USAGE: dict[CreatorPostType, CommentUsageMode] = {
    "commentary": "angle_driver",
    "insight": "nuance_layer",
    "teaching": "example_source",
    "relatable": "tone_signal",
    "inspiration": "ignore",
}

PILLAR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "data_engineering": (
        "data pipeline",
        "pipeline",
        "dbt",
        "airflow",
        "etl",
        "elt",
        "warehouse",
        "lakehouse",
        "snowflake",
        "databricks",
        "spark",
        "batch job",
        "orchestration",
        "data quality",
        "analytics engineering",
    ),
    "python_backend": (
        "python",
        "pandas",
        "sql",
        "api",
        "backend",
        "fastapi",
        "flask",
        "django",
        "rest",
        "microservice",
        "debugging",
        "traceback",
        "automation script",
    ),
    "ai_ml": (
        "ai",
        "llm",
        "llms",
        "agent",
        "agents",
        "machine learning",
        "model",
        "models",
        "feature engineering",
        "vector",
        "embedding",
        "retrieval",
        "rag",
        "guardrail",
        "prompt",
        "tool calling",
        "evaluation",
        "benchmark",
        "inference",
    ),
    "beginner_practice": (
        "excel",
        "sql basics",
        "learn python",
        "beginner",
        "starter",
        "first project",
        "dashboard",
        "analytics",
        "null",
        "missing values",
        "cleaning data",
    ),
    "career_insight": (
        "career",
        "learning",
        "interview",
        "mistake",
        "debugging pain",
        "open source",
        "build in public",
        "workflow",
        "mental model",
    ),
}

OFF_BRAND_MARKERS = (
    "celebrity",
    "football",
    "soccer",
    "fashion",
    "diet",
    "exercise timing",
    "dating",
    "movie review",
    "cryptocurrency price",
    "stock tip",
    "rust's memory model",
)


def _voice_profile_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "voice_profile.json"


def load_voice_profile() -> dict[str, Any]:
    path = _voice_profile_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


VOICE_PROFILE = load_voice_profile()


def get_day_tone_hint(day_name: str) -> str:
    return DAY_TONE_HINTS.get(day_name, "")


def get_template(post_type: str) -> str:
    return POST_TYPE_TEMPLATES.get(post_type, "")


def get_format_instruction(content_format: str) -> str:
    return FORMAT_OUTPUT_SPEC.get(content_format, FORMAT_OUTPUT_SPEC["text"])


def get_evidence_policy(post_type: str) -> dict[str, Any]:
    return dict(EVIDENCE_POLICIES.get(post_type, EVIDENCE_POLICIES["insight"]))


def get_originality_threshold(post_type: str) -> float:
    return float(ORIGINALITY_THRESHOLDS.get(post_type, ORIGINALITY_THRESHOLDS["insight"]))


def get_comment_usage(post_type: str) -> CommentUsageMode:
    normalized = normalize_creator_post_type(post_type)
    return COMMENT_INSIGHT_USAGE.get(normalized, "ignore")


def comment_usage_affects_subject(usage_mode: str) -> bool:
    return usage_mode in {"angle_driver", "nuance_layer", "example_source"}


def get_banned_words() -> tuple[str, ...]:
    words = VOICE_PROFILE.get("banned_words", [])
    return tuple(str(word).strip().lower() for word in words if str(word).strip())


def _weighted_choice(weights: dict[CreatorPostType, float], *, seed: str) -> CreatorPostType:
    population = list(weights.keys())
    rng = random.Random(seed)
    total = sum(max(weight, 0.0) for weight in weights.values())
    if total <= 0:
        return "insight"
    threshold = rng.uniform(0, total)
    running = 0.0
    for item in population:
        running += max(weights[item], 0.0)
        if threshold <= running:
            return item
    return population[-1]


def select_post_type(
    day_name: str,
    recent_types: list[str] | None = None,
    *,
    seed_date: date | None = None,
) -> CreatorPostType:
    recent_types = recent_types or []
    weights = {ptype: float(weight) for ptype, weight in POST_TYPE_WEIGHTS.get(day_name, POST_TYPE_WEIGHTS["Monday"]).items()}
    allowed = set(DAY_ALLOWED_POST_TYPES.get(day_name, CREATOR_POST_TYPES))
    weights = {ptype: weight for ptype, weight in weights.items() if ptype in allowed}

    for index, recent in enumerate(recent_types[:4]):
        if recent not in weights:
            continue
        decay = 0.5 if index == 0 else 0.65 if index == 1 else 0.78 if index == 2 else 0.88
        weights[recent] *= decay

    current_date = seed_date or date.today()
    seed = f"{current_date.isoformat()}::{day_name}::{','.join(recent_types[:4])}"
    return _weighted_choice(weights, seed=seed)


def select_content_format(
    day_name: str,
    recent_formats: list[str] | None = None,
    *,
    seed_date: date | None = None,
) -> ContentFormat:
    recent_formats = recent_formats or []
    weights = {
        content_format: float(weight)
        for content_format, weight in FORMAT_WEIGHTS_BY_DAY.get(day_name, FORMAT_WEIGHTS_BY_DAY["Monday"]).items()
    }

    for index, recent in enumerate(recent_formats[:4]):
        if recent not in weights:
            continue
        decay = 0.5 if index == 0 else 0.65 if index == 1 else 0.78 if index == 2 else 0.88
        weights[recent] *= decay

    current_date = seed_date or date.today()
    seed = f"{current_date.isoformat()}::{day_name}::format::{','.join(recent_formats[:4])}"
    return _weighted_choice(weights, seed=seed)


def classify_pillar(text: str) -> TopicPillar:
    haystack = text.lower()
    for pillar, keywords in PILLAR_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return pillar  # type: ignore[return-value]
    return ""


def passes_topic_filter(text: str) -> bool:
    haystack = text.lower()
    if any(marker in haystack for marker in OFF_BRAND_MARKERS):
        return False
    return bool(classify_pillar(haystack))


def normalize_creator_post_type(post_type: str) -> CreatorPostType:
    normalized = post_type.strip().lower()
    if normalized in CREATOR_POST_TYPES:
        return normalized  # type: ignore[return-value]
    return LEGACY_POST_TYPE_MAP.get(normalized, "insight")
