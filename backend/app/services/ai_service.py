import json
import re

from groq import Groq, GroqError
from pydantic import ValidationError

from app.config.logger import logger
from app.config.settings import settings
from app.schemas.lesson_plan_schema import LessonPlanAIOutput


class AIGenerationError(Exception):
    """Raised when the AI model output cannot be parsed or validated.

    Carries only a safe, client-facing message; the underlying detail is
    logged server-side and never surfaced to the caller. The API layer maps
    this to a 502 (bad upstream response).
    """


class AIServiceUnavailableError(AIGenerationError):
    """Raised when the Groq provider itself cannot be reached / fails.

    Covers network errors, timeouts, authentication/rate-limit failures and
    any other transport-level problem talking to Groq. It subclasses
    :class:`AIGenerationError` so existing ``except AIGenerationError`` handlers
    keep working, while the API layer can map it to a 503 (dependency
    unavailable). The underlying exception is logged server-side only — API
    keys, provider internals and raw messages are never surfaced.
    """


client = Groq(api_key=settings.GROQ_API_KEY)

_MODEL = settings.GROQ_MODEL

# The exact JSON shape the model must emit. Kept in the prompt so the model has
# a concrete target; the response is validated against LessonPlanAIOutput.
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
    """
    if raw is None:
        raise ValueError("Empty AI response")

    candidate = raw.strip()

    # Strip fenced code blocks like ```json\n{...}\n``` or ```\n{...}\n```.
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()

    # If there is still surrounding prose, slice from the first { to the last }.
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
        logger.error("Groq provider call failed: %s", type(exc).__name__)
        logger.debug("Groq failure detail", exc_info=exc)
        raise AIServiceUnavailableError(
            "The AI service is temporarily unavailable. Please try again later."
        ) from exc
    except Exception as exc:  # pragma: no cover - unexpected transport failure
        logger.exception("Unexpected error calling the AI provider")
        raise AIServiceUnavailableError(
            "The AI service is temporarily unavailable. Please try again later."
        ) from exc

    # Guard against an empty / malformed provider envelope before indexing it,
    # so a missing choice never raises an unhandled IndexError/AttributeError.
    raw = None
    try:
        if response is not None and response.choices:
            raw = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        logger.error("Malformed AI response envelope: %s", exc)
        raise AIGenerationError("AI generation failed to produce valid output.") from exc

    if raw is None or not str(raw).strip():
        logger.error("AI provider returned an empty response body")
        raise AIGenerationError("AI generation failed to produce valid output.")

    try:
        payload = _extract_json_payload(raw)
        data = json.loads(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Failed to parse AI lesson-plan JSON: %s", exc)
        logger.debug("Raw AI response was: %r", raw)
        raise AIGenerationError("AI generation failed to produce valid output.") from exc

    try:
        return LessonPlanAIOutput.model_validate(data)
    except ValidationError as exc:
        logger.error("AI lesson-plan JSON failed schema validation: %s", exc)
        raise AIGenerationError("AI generation failed to produce valid output.") from exc