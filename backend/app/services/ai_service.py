import anyio
import json
import re
from typing import Any

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
    """Raised when the Groq provider itself cannot be reached / fails or is unconfigured.

    Covers configuration errors, network errors, timeouts, authentication/rate-limit
    failures, unavailable models and any other transport-level problem talking to Groq.
    It subclasses :class:`AIGenerationError` so existing ``except AIGenerationError``
    handlers keep working, while the API layer can map it to a 503 (dependency
    unavailable). The underlying exception is logged server-side only — API
    keys, provider internals and raw messages are never surfaced.
    """


# Module-level client / model handles (can be monkeypatched by tests).
client: Any = None
_MODEL: str | None = None


def get_groq_client() -> Any:
    """Return a configured Groq client or raise AIServiceUnavailableError."""
    global client
    if client is not None:
        return client
    api_key = settings.GROQ_API_KEY
    if not api_key or not str(api_key).strip():
        logger.error("Groq API key is not configured in settings")
        raise AIServiceUnavailableError(
            "The AI service is not properly configured. Please contact the administrator."
        )
    return Groq(api_key=str(api_key).strip())


def get_groq_model() -> str:
    """Return the configured Groq model name or raise AIServiceUnavailableError."""
    global _MODEL
    model = _MODEL or settings.GROQ_MODEL
    if not model or not str(model).strip():
        logger.error("Groq model name is not configured in settings")
        raise AIServiceUnavailableError(
            "The AI service model is not properly configured. Please contact the administrator."
        )
    return str(model).strip()



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


def _call_groq_sync(prompt: str, model: str, client: Groq) -> Any:
    """Perform synchronous Groq API call inside a worker thread."""
    return client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        response_format={"type": "json_object"},
    )


async def generate_lesson_plan(text: str) -> LessonPlanAIOutput:
    """Generate a validated, structured lesson plan from syllabus text.

    Returns a ``LessonPlanAIOutput`` instance. Raises ``AIServiceUnavailableError``
    (mapped to 503) or ``AIGenerationError`` (mapped to 502) with safe, generic
    messages; underlying details and secrets are logged server-side only.
    """
    client = get_groq_client()
    model = get_groq_model()
    prompt = _build_prompt(text)

    # Talk to Groq defensively in a worker thread: any transport/provider failure
    # (network, timeout, auth, rate-limit, model unavailable, 5xx) becomes a
    # controlled, safe error rather than escaping as an unhandled 500.
    try:
        response = await anyio.to_thread.run_sync(_call_groq_sync, prompt, model, client)
    except GroqError as exc:
        status_code = getattr(exc, "status_code", None)
        logger.error(
            "Groq provider call failed: %s (status_code=%s)",
            type(exc).__name__,
            status_code,
        )
        logger.debug("Groq failure detail (model=%s)", model, exc_info=exc)
        raise AIServiceUnavailableError(
            "The AI service is temporarily unavailable. Please try again later."
        ) from exc
    except AIServiceUnavailableError:
        raise
    except Exception as exc:  # pragma: no cover - unexpected transport failure
        logger.exception("Unexpected error calling the AI provider (model=%s)", model)
        raise AIServiceUnavailableError(
            "The AI service is temporarily unavailable. Please try again later."
        ) from exc

    # Guard against an empty / malformed provider envelope before indexing it,
    # so a missing choice never raises an unhandled IndexError/AttributeError.
    raw = None
    try:
        if response is not None and getattr(response, "choices", None):
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