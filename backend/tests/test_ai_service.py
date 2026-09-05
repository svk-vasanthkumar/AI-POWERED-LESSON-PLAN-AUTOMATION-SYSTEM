"""Tests for the Groq-backed AI *enrichment* service (canonical-syllabus rework).

Since the canonical rework the AI model no longer generates the lesson plan; it
only enriches the canonical topics with pedagogy. These tests therefore exercise
the enrichment-only contract:

  * ``request_enrichment`` returns a validated ``LessonPlanEnrichment`` on
    success (the real Groq API is NEVER called — the module-level ``client`` is
    monkeypatched with a fully controlled fake),
  * provider/network failures become the controlled error taxonomy
    (``AIConfigurationError`` / ``AIRateLimitError`` / ``AIServiceUnavailableError``
    / ``AIGenerationError``) and NEVER leak provider internals / API keys,
  * malformed JSON / schema-validation / empty responses become
    ``AIGenerationError`` (mapped to 502 by the API),
  * ``classify_provider_error`` maps SDK exception *types* and HTTP status codes
    onto that taxonomy,
  * ``merge_enrichment`` is canonical-driven: the model can never add, drop,
    rename or reorder topics, invent hours or fabricate references.

Run: python -m pytest backend/tests/test_ai_service.py -q
"""

import asyncio
import types

import pytest
from groq import GroqError

from app.services import ai_service
from app.services.ai_service import (
    AIConfigurationError,
    AIGenerationError,
    AIRateLimitError,
    AIServiceUnavailableError,
    build_enrichment_prompt,
    classify_provider_error,
    merge_enrichment,
    request_enrichment,
)
from app.schemas.lesson_plan_schema import LessonPlanEnrichment
from app.schemas.syllabus_schema import (
    CanonicalOutcome,
    CanonicalSyllabus,
    CanonicalTopic,
    CanonicalUnit,
)


def _run(coro):
    return asyncio.run(coro)


def _canonical() -> CanonicalSyllabus:
    """A tiny but complete canonical syllabus (the authoritative structure)."""
    return CanonicalSyllabus(
        course_code="CS101",
        course_title="Intro to CS",
        units=[
            CanonicalUnit(
                unit_number=1,
                unit_title="Fundamentals",
                hours=3,
                hours_source="syllabus",
                topics=[
                    CanonicalTopic(
                        topic_id="U1-T1",
                        topic="Topic Alpha",
                        unit_number=1,
                        order=1,
                        hours=2,
                        hours_source="syllabus",
                    ),
                    CanonicalTopic(
                        topic_id="U1-T2",
                        topic="Topic Beta",
                        unit_number=1,
                        order=2,
                        hours=1,
                        hours_source="syllabus",
                    ),
                ],
            )
        ],
        course_outcomes=[CanonicalOutcome(outcome_id="CO1", description="Explain X")],
        textbooks=["Cormen, Introduction to Algorithms"],
        references=["Sedgewick, Algorithms"],
    )


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


_VALID_ENRICHMENT = """{
  "topics": [
    {
      "topic_id": "U1-T1",
      "subtopics": ["Bits", "Bytes"],
      "bloom_level": "Understand",
      "learning_outcomes": ["CO1"],
      "teaching_methods": ["Lecture"],
      "assessment_methods": ["Quiz"]
    }
  ],
  "outcomes": [{"outcome_id": "CO1", "bloom_level": "Apply"}],
  "overall_teaching_methods": ["Lecture"],
  "overall_assessment_methods": ["Quiz"]
}"""


# ---------------------------------------------------------------------------
# 1. Successful enrichment
# ---------------------------------------------------------------------------


def test_successful_enrichment_returns_validated_payload(patch_client):
    patch_client(lambda **kw: _envelope(_VALID_ENRICHMENT))

    enrichment = _run(request_enrichment(_canonical()))

    assert isinstance(enrichment, LessonPlanEnrichment)
    assert enrichment.topics[0].topic_id == "U1-T1"
    assert enrichment.topics[0].bloom_level == "Understand"


def test_prompt_lists_topic_ids_and_forbids_invention():
    prompt = build_enrichment_prompt(_canonical())
    # The exact canonical ids must be present ...
    assert "U1-T1" in prompt and "U1-T2" in prompt
    # ... and the model must be told it cannot change the structure.
    assert "Do NOT add, remove, rename, merge, split or reorder topics." in prompt


# ---------------------------------------------------------------------------
# 2. Provider / network failure -> AIServiceUnavailableError (503), no leak
# ---------------------------------------------------------------------------


def test_provider_failure_maps_to_unavailable_and_hides_secret(patch_client):
    secret_detail = "connection refused to https://api.groq.com key=sk-SECRET"

    def _boom(**kw):
        raise GroqError(secret_detail)

    patch_client(_boom)

    with pytest.raises(AIServiceUnavailableError) as exc:
        _run(request_enrichment(_canonical()))

    assert secret_detail not in str(exc.value)
    assert "sk-SECRET" not in str(exc.value)


def test_unexpected_transport_error_maps_to_unavailable(patch_client):
    def _boom(**kw):
        raise RuntimeError("socket exploded")

    patch_client(_boom)

    with pytest.raises(AIServiceUnavailableError):
        _run(request_enrichment(_canonical()))


# ---------------------------------------------------------------------------
# 3. Malformed / invalid model output -> AIGenerationError (502)
# ---------------------------------------------------------------------------


def test_malformed_json_maps_to_generation_error(patch_client):
    patch_client(lambda **kw: _envelope("this is not json at all"))

    with pytest.raises(AIGenerationError) as exc:
        _run(request_enrichment(_canonical()))

    assert not isinstance(exc.value, AIServiceUnavailableError)


def test_schema_validation_failure_maps_to_generation_error(patch_client):
    # Valid JSON, but ``topics`` is the wrong type (a string, not a list).
    patch_client(lambda **kw: _envelope('{"topics": "not-a-list"}'))

    with pytest.raises(AIGenerationError) as exc:
        _run(request_enrichment(_canonical()))

    assert not isinstance(exc.value, AIServiceUnavailableError)


def test_empty_response_maps_to_generation_error(patch_client):
    patch_client(lambda **kw: _envelope(""))

    with pytest.raises(AIGenerationError):
        _run(request_enrichment(_canonical()))


def test_no_choices_maps_to_generation_error(patch_client):
    patch_client(lambda **kw: types.SimpleNamespace(choices=[]))

    with pytest.raises(AIGenerationError):
        _run(request_enrichment(_canonical()))


# ---------------------------------------------------------------------------
# 4. Provider-error taxonomy (classify_provider_error)
#
# The real SDK status errors need an httpx.Response to construct, so these use
# lightweight fakes that reproduce the two signals classify relies on: the
# exception *type name* and an HTTP *status code*.
# ---------------------------------------------------------------------------


def _named_exc(name, status=None):
    exc = type(name, (Exception,), {})("boom")
    if status is not None:
        exc.status_code = status
    return exc


@pytest.mark.parametrize(
    "name,status,expected",
    [
        ("AuthenticationError", 401, AIConfigurationError),
        ("PermissionDeniedError", 403, AIConfigurationError),
        ("RateLimitError", 429, AIRateLimitError),
        ("BadRequestError", 400, AIGenerationError),
        ("UnprocessableEntityError", 422, AIGenerationError),
        ("NotFoundError", 404, AIConfigurationError),
        ("APIConnectionError", None, AIServiceUnavailableError),
        ("InternalServerError", 500, AIServiceUnavailableError),
    ],
)
def test_classify_provider_error_taxonomy(name, status, expected):
    result = classify_provider_error(_named_exc(name, status))
    assert isinstance(result, expected)
    # A bad-request is a 502 generation error, NOT a retryable 503.
    if expected is AIGenerationError:
        assert not isinstance(result, AIServiceUnavailableError)


def test_classified_errors_never_leak_provider_message():
    leaky = _named_exc("AuthenticationError", 401)
    leaky.args = ("key=sk-TOPSECRET invalid",)
    result = classify_provider_error(leaky)
    assert "sk-TOPSECRET" not in str(result)


# ---------------------------------------------------------------------------
# 5. merge_enrichment — canonical is authoritative (enrichment-only contract)
# ---------------------------------------------------------------------------


def test_merge_preserves_every_canonical_topic_in_order():
    canonical = _canonical()
    enrichment = LessonPlanEnrichment.model_validate(
        {
            "topics": [
                {"topic_id": "U1-T1", "bloom_level": "Understand",
                 "teaching_methods": ["Lecture"]},
                # An enrichment entry for a topic that does NOT exist — must be
                # discarded silently, never added to the plan.
                {"topic_id": "U9-T9", "bloom_level": "Create"},
            ]
        }
    )

    plan = merge_enrichment(canonical, enrichment)

    ids = [t.topic_id for u in plan.units for t in u.topics]
    assert ids == ["U1-T1", "U1-T2"]  # exactly the canonical topics, in order
    # Enrichment applied to the known topic ...
    t1 = plan.units[0].topics[0]
    assert t1.bloom_level == "Understand"
    assert t1.teaching_methods == ["Lecture"]
    # ... hours always come from the syllabus, never the model.
    assert t1.estimated_hours == 2
    assert plan.units[0].topics[1].estimated_hours == 1


def test_merge_without_enrichment_keeps_topics_with_blank_pedagogy():
    """An AI failure (enrichment=None) must still yield a complete plan."""
    plan = merge_enrichment(_canonical(), None)

    ids = [t.topic_id for u in plan.units for t in u.topics]
    assert ids == ["U1-T1", "U1-T2"]
    t1 = plan.units[0].topics[0]
    assert t1.bloom_level is None
    assert t1.teaching_methods == []
    # References always come from the syllabus.
    assert "Cormen, Introduction to Algorithms" in plan.references


def test_merge_drops_unknown_learning_outcomes():
    canonical = _canonical()
    enrichment = LessonPlanEnrichment.model_validate(
        {
            "topics": [
                {"topic_id": "U1-T1", "learning_outcomes": ["CO1", "CO_FAKE"]},
            ]
        }
    )
    plan = merge_enrichment(canonical, enrichment)
    assert plan.units[0].topics[0].learning_outcomes == ["CO1"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
