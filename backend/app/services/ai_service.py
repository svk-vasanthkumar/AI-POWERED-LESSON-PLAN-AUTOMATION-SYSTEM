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
  "topics": [
    {
      "topic_id": "U1-T1",
      "subtopics": ["string"],
      "bloom_level": "Understand",
      "learning_outcomes": ["CO1"],
      "teaching_methods": ["Lecture"],
      "assessment_methods": ["Quiz"]
    }
  ],
  "outcomes": [{"outcome_id": "CO1", "bloom_level": "Apply"}],
  "overall_teaching_methods": ["string"],
  "overall_assessment_methods": ["string"]
}"""


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_enrichment_prompt(canonical: CanonicalSyllabus) -> str:
    """Build the enrichment prompt from the canonical syllabus.

    The prompt lists the exact topic ids that exist. The model is told, in the
    strongest terms available, that it may not invent structure, hours or
    references — those are supplied by the syllabus and are not its concern.
    """
    lines: list[str] = []
    for unit in canonical.units:
        lines.append(f"Unit {unit.unit_number}: {unit.unit_title}".rstrip(": "))
        for topic in unit.topics:
            lines.append(f"  {topic.topic_id} | {topic.topic}")
    topic_listing = "\n".join(lines)

    outcome_listing = (
        "\n".join(
            f"  {outcome.outcome_id}: {outcome.description}".rstrip(": ")
            for outcome in canonical.course_outcomes
        )
        or "  (none defined in the syllabus)"
    )

    course_label = " ".join(
        part for part in (canonical.course_code, canonical.course_title) if part
    )

    return f"""You are an experienced college professor advising on teaching pedagogy.

The course structure below is FIXED. It was extracted from the official
syllabus. Your ONLY task is to attach pedagogical metadata to the topics that
already exist.

Course: {course_label}

Topics (topic_id | topic name):
{topic_listing}

Course outcomes defined by the syllabus:
{outcome_listing}

Return a single JSON object that EXACTLY matches this schema:

{_SCHEMA_HINT}

Absolute rules:
- Return JSON only: no Markdown, no code fences, no prose before or after.
- Use ONLY the topic_id values listed above. Do NOT invent new topic ids.
- Do NOT add, remove, rename, merge, split or reorder topics.
- Do NOT return teaching hours, dates, units or textbook references. Those come
  from the syllabus and are not yours to decide.
- Do NOT return topic names; the topic_id is enough to identify a topic.
- learning_outcomes must reference only the course outcome ids listed above.
- bloom_level must be one of: {", ".join(BLOOM_LEVELS)}.
- Choose realistic teaching methods (e.g. Lecture, Discussion, Case Study,
  Demonstration, Lab, Flipped Classroom, Problem Solving).
- Choose realistic assessment methods (e.g. Quiz, Assignment, Internal
  Assessment, Seminar, Project, Viva).
"""


# ---------------------------------------------------------------------------
# Provider plumbing
# ---------------------------------------------------------------------------


def _extract_json_payload(raw: str) -> str:
    """Best-effort recovery of a JSON object from a model response.

    Handles the common failure modes even though we request json_object:
    - ```json ... ``` (or plain ``` ... ```) fenced blocks
    - leading/trailing prose around the object
    """
    if raw is None:
        raise ValueError("Empty AI response")

    candidate = raw.strip()

    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()

    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]

    return candidate


def _provider_status_code(exc: Exception) -> int | None:
    """Extract an HTTP status code from a Groq SDK exception, if present."""
    for attribute in ("status_code", "http_status", "code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def classify_provider_error(exc: Exception) -> AIGenerationError:
    """Map a provider exception onto this module's error taxonomy.

    Classification uses the SDK exception type first (``AuthenticationError``,
    ``RateLimitError``, ``BadRequestError`` …) and falls back to the HTTP status
    code, so it keeps working across SDK versions. Provider messages are never
    forward to the client.
    """
    name = type(exc).__name__
    status = _provider_status_code(exc)

    if "Authentication" in name or "Permission" in name or status in (401, 403):
        return AIConfigurationError(
            "The AI service is not configured correctly. Please contact an administrator."
        )
    if "RateLimit" in name or status == 429:
        return AIRateLimitError(
            "The AI service is rate limited right now. Please retry in a moment."
        )
    if "BadRequest" in name or "UnprocessableEntity" in name or status in (400, 422):
        # Our request was rejected (e.g. prompt too long for the model). This is
        # an upstream contract problem, not a transient outage.
        return AIGenerationError(
            "The AI service could not process this request. Please try again."
        )
    if "NotFound" in name or status == 404:
        return AIConfigurationError(
            "The configured AI model is unavailable. Please contact an administrator."
        )
    return AIServiceUnavailableError(
        "The AI service is temporarily unavailable. Please try again later."
    )


def _call_groq(prompt: str) -> str | None:
    """Synchronous Groq call. Executed on a worker thread by the caller."""
    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    if response is None or not response.choices:
        return None
    return response.choices[0].message.content


async def request_enrichment(canonical: CanonicalSyllabus) -> LessonPlanEnrichment:
    """Ask the model for pedagogy metadata for the canonical topics.

    Raises one of the module's error classes on failure; the caller decides
    whether to degrade gracefully (persist the canonical plan without pedagogy)
    or surface the error.
    """
    prompt = build_enrichment_prompt(canonical)

    try:
        # The Groq SDK is synchronous; running it inline would block the event
        # loop (and therefore every other request) for the whole model call.
        raw = await asyncio.to_thread(_call_groq, prompt)
    except GroqError as exc:
        logger.error("Groq provider call failed: %s", type(exc).__name__)
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