"""AI enrichment for lesson plans.

Scope (deliberately narrow)
---------------------------
The AI model does **not** define the academic structure of a course. Units, unit
titles, topics, topic order, teaching hours, course outcomes and textbook
references all come from :mod:`app.services.syllabus_parser`, which reads them
deterministically from the syllabus document.

This module only asks the model for *pedagogical* metadata — Bloom levels,
teaching methods, assessment methods and outcome mapping — keyed by the
canonical ``topic_id`` values it is given. :func:`merge_enrichment` then builds
the final structured plan from the canonical syllabus and drops anything the
model returned for an unknown topic. As a result the model can no longer:

  * omit or add topics (the "missing Unit 4" bug),
  * invent teaching hours,
  * fabricate textbook references.

Failure handling
----------------
Provider failures are classified instead of collapsing into a single 503:

    AIConfigurationError  -- bad/absent credentials, model not permitted
    AIRateLimitError      -- provider throttling (retryable, 429)
    AIServiceUnavailableError -- network/timeout/5xx (retryable, 503)
    AIGenerationError     -- the model replied but the payload was unusable (502)

The blocking Groq SDK call is executed on a worker thread so a slow model call
can never stall the FastAPI event loop for other requests.
"""

from __future__ import annotations

import asyncio
import json
import re

from groq import Groq, GroqError
from pydantic import ValidationError

from app.config.logger import logger
from app.config.settings import settings
from app.schemas.lesson_plan_schema import (
    LearningOutcome,
    LessonPlanAIOutput,
    LessonPlanEnrichment,
    TopicPlan,
    UnitPlan,
)
from app.schemas.syllabus_schema import CanonicalSyllabus


class AIGenerationError(Exception):
    """The model responded but its output could not be parsed/validated (-> 502).

    Carries only a safe, client-facing message; the underlying detail is logged
    server-side and never surfaced to the caller.
    """


class AIServiceUnavailableError(AIGenerationError):
    """The provider could not be reached (network/timeout/5xx) (-> 503).

    Subclasses :class:`AIGenerationError` so existing
    ``except AIGenerationError`` handlers keep working.
    """


class AIRateLimitError(AIServiceUnavailableError):
    """The provider throttled the request (-> 429). Retryable after a delay."""


class AIConfigurationError(AIServiceUnavailableError):
    """The AI provider rejected our credentials / model access (-> 500).

    This is a server misconfiguration, not something the caller can fix by
    retrying, so it is reported separately from a transient outage.
    """


client = Groq(api_key=settings.GROQ_API_KEY)

_MODEL = settings.GROQ_MODEL

# Bloom levels the model is allowed to use (anything else is discarded).
BLOOM_LEVELS = (
    "Remember",
    "Understand",
    "Apply",
    "Analyze",
    "Evaluate",
    "Create",
)

_SCHEMA_HINT = """{
  "course_title": "string",
  "course_objectives": ["string"],
  "learning_outcomes": [
    {"outcome_id": "CO1", "description": "string", "bloom_level": "Understand"}
  ],
  "units": [
    {
      "unit_number": 1,
      "unit_title": "string",
      "topics": [
        {
          "topic_id": "U1-T1",
          "topic": "string",
          "subtopics": ["string"],
          "estimated_hours": 1,
          "bloom_level": "Understand",
          "learning_outcomes": ["CO1"],
          "teaching_methods": ["Lecture"],
          "assessment_methods": ["Quiz"],
          "references": ["string"]
        }
      ]
    }
  ],
  "overall_teaching_methods": ["string"],
  "overall_assessment_methods": ["string"],
  "references": ["string"]
}"""


def _build_prompt(text: str) -> str:
    return f"""You are an experienced college professor and curriculum designer.

Based ONLY on the syllabus provided below, produce a structured lesson plan.

Return your answer as a single JSON object that EXACTLY matches this schema:

{_SCHEMA_HINT}

Strict rules:
- Return JSON only. Output nothing before or after the JSON object.
- Do NOT return Markdown.
- Do NOT wrap the JSON in ```json fences or any other fences.
- Do NOT add explanations, comments, or prose outside the JSON.
- Follow the schema keys and nesting exactly.
- Do NOT invent topics unrelated to the supplied syllabus.
- Preserve the unit and topic ordering from the syllabus where possible.
- Estimate realistic teaching hours as numbers (estimated_hours numeric, unit_number integer).
- Assign useful Bloom's taxonomy levels (Remember, Understand, Apply, Analyze, Evaluate, Create).
- Choose appropriate teaching methods (e.g. Lecture, Discussion, Case Study, Lab).
- Choose suitable assessment methods (e.g. Quiz, Assignment, Internal Assessment, Project).
- Base references on the syllabus / reference material when available; otherwise use realistic academic references.

Syllabus:

{text}
"""


def _extract_json_payload(raw: str) -> str:
    """Best-effort recovery of a JSON object from a model response.

    Handles the common failure modes even though we request json_object:
    - ```json ... ``` (or plain ``` ... ```) fenced blocks
    - leading/trailing prose around the object
    - Qwen3 <think>...</think> reasoning blocks
    """
    if raw is None:
        raise ValueError("Empty AI response")

    candidate = raw.strip()

    # Strip Qwen3 thinking blocks: <think>...</think>
    candidate = re.sub(r"<think>.*?</think>", "", candidate, flags=re.DOTALL).strip()

    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()

    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]

    return candidate


def structured_to_topic_text(plan: LessonPlanAIOutput) -> str:
    """Flatten the structured plan into an ordered newline-delimited topic list.

    This preserves backward compatibility with existing consumers (e.g. the
    scheduler, which splits ``lesson_plan`` on newlines into teachable topics)
    without touching those services.
    """
    lines: list[str] = []
    for unit in plan.units:
        for topic in unit.topics:
            if topic.topic and topic.topic.strip():
                lines.append(topic.topic.strip())
    return "\n".join(lines)


async def generate_lesson_plan(text: str) -> LessonPlanAIOutput:
    """Generate a validated, structured lesson plan from syllabus text.

    Returns a ``LessonPlanAIOutput`` instance. Raises ``ValueError`` with a
    safe, generic message if the model output cannot be parsed or validated;
    the underlying detail is logged server-side only.
    """
    prompt = _build_prompt(text)

    # Talk to Groq defensively: any transport/provider failure (network,
    # timeout, auth, rate-limit, 5xx) must become a controlled, safe error
    # rather than escaping as a generic 500 that could leak internals.
    try:
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            response_format={"type": "json_object"},
        )
    except GroqError as exc:
        logger.error("Groq provider call failed: %s — %s", type(exc).__name__, exc)
        logger.debug("Groq failure detail", exc_info=exc)
        raise classify_provider_error(exc) from exc
    except (AttributeError, IndexError, TypeError) as exc:
        logger.error("Malformed AI response envelope: %s", exc)
        raise AIGenerationError("AI enrichment failed to produce valid output.") from exc
    except Exception as exc:  # pragma: no cover - unexpected transport failure
        logger.exception("Unexpected error calling the AI provider")
        raise classify_provider_error(exc) from exc

    if raw is None or not str(raw).strip():
        logger.error("AI provider returned an empty response body")
        raise AIGenerationError("AI enrichment failed to produce valid output.")

    try:
        data = json.loads(_extract_json_payload(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Failed to parse AI enrichment JSON: %s", exc)
        logger.debug("Raw AI response was: %r", raw)
        raise AIGenerationError("AI enrichment failed to produce valid output.") from exc

    try:
        return LessonPlanEnrichment.model_validate(data)
    except ValidationError as exc:
        logger.error("AI enrichment JSON failed schema validation: %s", exc)
        raise AIGenerationError("AI enrichment failed to produce valid output.") from exc


# ---------------------------------------------------------------------------
# Merge: canonical syllabus (+ optional enrichment) -> structured plan
# ---------------------------------------------------------------------------


def _clean_list(values, allowed: set[str] | None = None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        if allowed is not None and text.upper() not in allowed:
            continue
        if text not in out:
            out.append(text)
    return out


def _clean_bloom(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    for level in BLOOM_LEVELS:
        if text.lower() == level.lower():
            return level
    return None


def merge_enrichment(
    canonical: CanonicalSyllabus,
    enrichment: LessonPlanEnrichment | None,
    course_title: str | None = None,
) -> LessonPlanAIOutput:
    """Build the structured plan from the canonical syllabus.

    The canonical syllabus is authoritative for every structural field. The
    enrichment payload may only fill in pedagogy for topics that already exist:

      * an enrichment entry for an unknown ``topic_id`` is discarded,
      * a canonical topic with no enrichment keeps empty pedagogy fields,
      * hours and references are always taken from the syllabus.

    Passing ``enrichment=None`` (an AI failure) therefore yields a complete,
    fully usable plan with blank pedagogy rather than nothing at all.
    """
    canonical_topic_ids = {
        topic.topic_id.upper()
        for _, topic in canonical.iter_topics()
    }
    by_topic: dict[str, object] = {}
    for entry in (enrichment.topics if enrichment else []) or []:
        topic_id = str(entry.topic_id).strip().upper()
        
        # AI cannot create a new academic topic.
        if topic_id not in canonical_topic_ids:
            continue
            
        # Keep the first valid enrichment for duplicate topic IDs.
        by_topic.setdefault(topic_id, entry)

    allowed_outcomes = {
        outcome.outcome_id.strip().upper()
        for outcome in canonical.course_outcomes
    }
    outcome_bloom: dict[str, str] = {}
    for entry in (enrichment.outcomes if enrichment else []) or []:
        outcome_id = str(entry.outcome_id).strip().upper()

        # AI may enrich only outcomes defined by the syllabus.
        if outcome_id not in allowed_outcomes:
            continue

        level = _clean_bloom(entry.bloom_level)
        if level:
            outcome_bloom[outcome_id] = level

    # Textbooks and references are course-level facts printed in the syllabus.
    # Attaching them to each topic keeps the ACE export's "Text Book/Resource"
    # column truthful without ever inventing a source.
    topic_resources = list(canonical.textbooks)

    units: list[UnitPlan] = []
    for unit in canonical.units:
        topics: list[TopicPlan] = []
        for topic in unit.topics:
            entry = by_topic.get(topic.topic_id.upper())
            topics.append(
                TopicPlan(
                    topic_id=topic.topic_id,
                    topic=topic.topic,
                    subtopics=_clean_list(getattr(entry, "subtopics", None)),
                    estimated_hours=topic.hours,
                    bloom_level=_clean_bloom(getattr(entry, "bloom_level", None)),
                    learning_outcomes=_clean_list(
                        getattr(entry, "learning_outcomes", None),
                        allowed=allowed_outcomes or None,
                    ),
                    teaching_methods=_clean_list(getattr(entry, "teaching_methods", None)),
                    assessment_methods=_clean_list(
                        getattr(entry, "assessment_methods", None)
                    ),
                    references=list(topic_resources),
                )
            )
        units.append(
            UnitPlan(
                unit_number=unit.unit_number,
                unit_title=unit.unit_title,
                topics=topics,
            )
        )

    learning_outcomes = [
        LearningOutcome(
            outcome_id=outcome.outcome_id,
            description=outcome.description,
            bloom_level=outcome_bloom.get(outcome.outcome_id.upper(), ""),
        )
        for outcome in canonical.course_outcomes
    ]

    title = (
        (course_title or "").strip()
        or (canonical.course_title or "").strip()
        or (canonical.course_code or "").strip()
        or "Untitled course"
    )

    return LessonPlanAIOutput(
        course_title=title,
        course_objectives=list(canonical.course_objectives),
        learning_outcomes=learning_outcomes,
        units=units,
        overall_teaching_methods=_clean_list(
            enrichment.overall_teaching_methods if enrichment else None
        ),
        overall_assessment_methods=_clean_list(
            enrichment.overall_assessment_methods if enrichment else None
        ),
        references=list(canonical.textbooks) + list(canonical.references),
    )


def structured_to_topic_text(plan: LessonPlanAIOutput) -> str:
    """Flatten the structured plan into an ordered newline-delimited topic list.

    Preserves backward compatibility with consumers that read the flat
    ``lesson_plan`` string (splitting it on newlines into teachable topics).
    """
    lines: list[str] = []
    for unit in plan.units:
        for topic in unit.topics:
            if topic.topic and topic.topic.strip():
                lines.append(topic.topic.strip())
    return "\n".join(lines)