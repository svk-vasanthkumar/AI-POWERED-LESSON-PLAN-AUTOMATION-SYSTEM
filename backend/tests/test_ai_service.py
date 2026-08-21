"""Tests for the Groq-backed lesson-plan AI service error handling (Task #8.2).

The real Groq API is NEVER called: the module-level ``client`` is monkeypatched
with a fake whose ``chat.completions.create`` is fully controlled per test. This
verifies:

  * a successful generation returns a validated ``LessonPlanAIOutput``,
  * a provider/network failure (any ``GroqError``) becomes the controlled
    ``AIServiceUnavailableError`` (mapped to 503 by the API) without leaking
    provider internals / API keys,
  * malformed JSON becomes ``AIGenerationError`` (mapped to 502),
  * schema-validation failure becomes ``AIGenerationError``,
  * an empty valid response becomes ``AIGenerationError``.

Run: python -m pytest backend/tests/test_ai_service.py -q
"""

import asyncio
import types

import pytest
from groq import GroqError

from app.services import ai_service
from app.services.ai_service import (
    AIGenerationError,
    AIServiceUnavailableError,
    generate_lesson_plan,
)
from app.schemas.lesson_plan_schema import LessonPlanAIOutput


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake Groq client plumbing
# ---------------------------------------------------------------------------


def _envelope(content):
    """Build a minimal object mimicking a Groq chat-completion response."""
    message = types.SimpleNamespace(content=content)
    choice = types.SimpleNamespace(message=message)
    return types.SimpleNamespace(choices=[choice])


class _FakeCompletions:
    def __init__(self, behavior):
        self._behavior = behavior

    def create(self, **kwargs):
        return self._behavior(**kwargs)


class _FakeClient:
    def __init__(self, behavior):
        self.chat = types.SimpleNamespace(completions=_FakeCompletions(behavior))


@pytest.fixture()
def patch_client(monkeypatch):
    def _install(behavior):
        monkeypatch.setattr(ai_service, "client", _FakeClient(behavior))

    return _install


_VALID_PAYLOAD = """{
  "course_title": "Intro to CS",
  "course_objectives": ["Understand basics"],
  "learning_outcomes": [
    {"outcome_id": "CO1", "description": "Explain X", "bloom_level": "Understand"}
  ],
  "units": [
    {"unit_number": 1, "unit_title": "Fundamentals",
     "topics": [{"topic_id": "U1-T1", "topic": "Topic Alpha", "estimated_hours": 2}]}
  ]
}"""


# ---------------------------------------------------------------------------
# 1. Successful generation
# ---------------------------------------------------------------------------

def test_successful_generation_returns_validated_plan(patch_client):
    patch_client(lambda **kw: _envelope(_VALID_PAYLOAD))

    plan = _run(generate_lesson_plan("Some syllabus text"))

    assert isinstance(plan, LessonPlanAIOutput)
    assert plan.units[0].topics[0].topic == "Topic Alpha"


# ---------------------------------------------------------------------------
# 2. Provider / network failure -> AIServiceUnavailableError (503), no leak
# ---------------------------------------------------------------------------

def test_provider_network_failure_maps_to_unavailable(patch_client):
    secret_detail = "connection refused to https://api.groq.com key=sk-SECRET"

    def _boom(**kw):
        raise GroqError(secret_detail)

    patch_client(_boom)

    with pytest.raises(AIServiceUnavailableError) as exc:
        _run(generate_lesson_plan("text"))

    # The client-facing message must never contain provider internals / keys.
    assert secret_detail not in str(exc.value)
    assert "sk-SECRET" not in str(exc.value)


def test_unexpected_transport_error_maps_to_unavailable(patch_client):
    def _boom(**kw):
        raise RuntimeError("socket exploded")

    patch_client(_boom)

    with pytest.raises(AIServiceUnavailableError):
        _run(generate_lesson_plan("text"))


# ---------------------------------------------------------------------------
# 3. Malformed JSON -> AIGenerationError (502)
# ---------------------------------------------------------------------------

def test_malformed_json_maps_to_generation_error(patch_client):
    patch_client(lambda **kw: _envelope("this is not json at all"))

    with pytest.raises(AIGenerationError) as exc:
        _run(generate_lesson_plan("text"))

    # Not the unavailable subclass — this is a bad-output (502) condition.
    assert not isinstance(exc.value, AIServiceUnavailableError)


# ---------------------------------------------------------------------------
# 4. Schema validation failure -> AIGenerationError (502)
# ---------------------------------------------------------------------------

def test_schema_validation_failure_maps_to_generation_error(patch_client):
    # Valid JSON, but structurally wrong: required ``course_title`` is absent
    # and a unit violates the schema (missing unit_title, unit_number < 1).
    patch_client(
        lambda **kw: _envelope('{"units": [{"unit_number": 0}]}')
    )

    with pytest.raises(AIGenerationError) as exc:
        _run(generate_lesson_plan("text"))

    assert not isinstance(exc.value, AIServiceUnavailableError)


# ---------------------------------------------------------------------------
# 5. Empty response body -> AIGenerationError (502)
# ---------------------------------------------------------------------------

def test_empty_response_maps_to_generation_error(patch_client):
    patch_client(lambda **kw: _envelope(""))

    with pytest.raises(AIGenerationError):
        _run(generate_lesson_plan("text"))


def test_no_choices_maps_to_generation_error(patch_client):
    import types as _t

    patch_client(lambda **kw: _t.SimpleNamespace(choices=[]))

    with pytest.raises(AIGenerationError):
        _run(generate_lesson_plan("text"))


# ---------------------------------------------------------------------------
# 6. Specific Groq error cases (auth, rate limit, unavailable model)
# ---------------------------------------------------------------------------

def test_groq_auth_failure_maps_to_unavailable(patch_client):
    def _auth_err(**kw):
        err = GroqError("Invalid API key")
        err.status_code = 401
        raise err

    patch_client(_auth_err)
    with pytest.raises(AIServiceUnavailableError) as exc:
        _run(generate_lesson_plan("text"))
    assert "Invalid API key" not in str(exc.value)


def test_groq_rate_limit_maps_to_unavailable(patch_client):
    def _rate_err(**kw):
        err = GroqError("Rate limit exceeded")
        err.status_code = 429
        raise err

    patch_client(_rate_err)
    with pytest.raises(AIServiceUnavailableError):
        _run(generate_lesson_plan("text"))


def test_groq_model_not_found_maps_to_unavailable(patch_client):
    def _model_err(**kw):
        err = GroqError("Model llama-3.3-70b-versatile not found")
        err.status_code = 404
        raise err

    patch_client(_model_err)
    with pytest.raises(AIServiceUnavailableError):
        _run(generate_lesson_plan("text"))


def test_fenced_json_recovery_succeeds(patch_client):
    fenced = f"```json\n{_VALID_PAYLOAD}\n```"
    patch_client(lambda **kw: _envelope(fenced))

    plan = _run(generate_lesson_plan("syllabus text"))
    assert isinstance(plan, LessonPlanAIOutput)
    assert plan.course_title == "Intro to CS"


def test_missing_groq_model_raises_configuration_error(monkeypatch):
    monkeypatch.setattr(ai_service, "client", None)
    monkeypatch.setattr(ai_service.settings, "GROQ_MODEL", "")
    with pytest.raises(AIServiceUnavailableError) as exc:
        _run(generate_lesson_plan("text"))
    assert "configured" in str(exc.value).lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

