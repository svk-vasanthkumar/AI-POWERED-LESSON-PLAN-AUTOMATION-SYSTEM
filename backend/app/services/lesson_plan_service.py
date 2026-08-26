"""Lesson-plan generation & lifecycle service.

Generation pipeline (the canonical-syllabus rework — Task #6)::

    syllabus document text
        -> parse_syllabus            (deterministic canonical structure)
        -> request_enrichment        (AI pedagogy ONLY; may fail/degrade)
        -> merge_enrichment          (canonical + pedagogy -> structured plan)
        -> validate_topic_coverage   (structured plan == canonical, or refuse)
        -> persist lesson plan        (structured_plan + provenance)

The syllabus is the single source of truth. The AI model can only *enrich* the
canonical topics; it can never add, drop, rename or reorder them (see
``app.services.ai_service``). If the enrichment call fails for any reason the
plan is still saved — every canonical topic is preserved, only the pedagogy
fields stay empty — so a transient Groq outage can never make syllabus topics
disappear.

Coverage is validated against the canonical syllabus before anything is stored;
an incomplete plan is refused (:class:`LessonPlanCoverageError` -> 422) rather
than silently saved.
"""

from __future__ import annotations

from bson import ObjectId

from app.config.logger import logger
from app.database.mongodb import get_database
from app.models.lesson_plan_model import create_lesson_plan_document
from app.services.ai_service import (
    AIGenerationError,
    merge_enrichment,
    request_enrichment,
    structured_to_topic_text,
)
from app.services.lesson_plan_validation import validate_topic_coverage
from app.services.syllabus_parser import SyllabusParseError, parse_syllabus
from app.utils.object_id import to_object_id


class LessonPlanInUseError(Exception):
    """Raised when a lesson plan cannot be deleted because records depend on it.

    The API layer maps this to a controlled 409 CONFLICT. Deleting the lesson
    plan would otherwise orphan the generated schedules that reference it via
    ``lesson_plan_id``, so restriction is preferred over a destructive cascade
    (the project has no deliberate cascade policy).
    """

    def __init__(self, dependencies: dict[str, int]):
        self.dependencies = dependencies
        summary = ", ".join(f"{count} {name}" for name, count in dependencies.items())
        super().__init__(
            "Lesson plan cannot be deleted while it is referenced by other "
            f"records ({summary}). Remove them first."
        )


class LessonPlanCoverageError(Exception):
    """Raised when an assembled plan does not fully cover the canonical syllabus.

    The merge is canonical-driven so this should never happen in practice, but
    it is a hard guard: an incomplete plan is refused (API -> 422) rather than
    silently persisted. Carries the coverage report so the caller can explain
    exactly which topics are missing/duplicated/reordered.
    """

    def __init__(self, coverage: dict):
        self.coverage = coverage or {}
        missing = self.coverage.get("missing_topics") or []
        super().__init__(
            "The generated lesson plan does not fully cover the syllabus "
            f"({len(missing)} topic(s) missing). Generation was refused."
        )


def _id_variants(value) -> list:
    """Both ObjectId and string forms of an id (legacy-compatible queries)."""
    variants = [value, str(value)]
    if not isinstance(value, ObjectId):
        try:
            variants.append(ObjectId(str(value)))
        except Exception:
            pass
    seen: set = set()
    unique: list = []
    for item in variants:
        key = (type(item).__name__, str(item))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


async def generate_and_save_lesson_plan(syllabus_id: str) -> dict:
    """Generate and persist a lesson plan from a syllabus (Task #6 pipeline).

    Ownership is enforced by the API layer (a faculty may only generate for a
    course they own); this service performs the deterministic-first pipeline.

    Raises:
        ValueError: the syllabus does not exist (-> 404).
        SyllabusParseError: the syllabus text could not be parsed into units +
            topics (-> 422); generation is refused rather than falling back to
            an AI-invented structure.
        LessonPlanCoverageError: the assembled plan does not cover every
            canonical topic (-> 422).
    """
    db = get_database()

    # Validate & convert the incoming id via the shared helper so a malformed
    # id returns a clean 400 instead of an unhandled 500.
    syllabus_oid = to_object_id(syllabus_id, field="syllabus_id")

    syllabus = await db.syllabi.find_one({"_id": syllabus_oid})
    if syllabus is None:
        raise ValueError("Syllabus not found")

    # 1) Deterministic canonical structure — the source of truth. A document
    #    whose structure cannot be recovered raises SyllabusParseError (-> 422)
    #    so a fabricated structure can never reach a lesson plan.
    canonical = parse_syllabus(syllabus.get("text") or "")

    # 2) AI enrichment (pedagogy only). Any failure degrades gracefully: the
    #    canonical topics are still persisted with empty pedagogy, and the
    #    failure is recorded on the plan for auditing. Topics are never lost.
    enrichment = None
    enrichment_status: dict = {"status": "ok", "reason": None}
    try:
        enrichment = await request_enrichment(canonical)
    except AIGenerationError as exc:
        logger.warning(
            "AI enrichment failed (%s); persisting canonical-only plan for "
            "syllabus %s",
            type(exc).__name__,
            syllabus_oid,
        )
        enrichment_status = {"status": "failed", "reason": str(exc)}

    # 3) Merge: canonical (authoritative) + optional pedagogy -> structured plan.
    structured = merge_enrichment(
        canonical, enrichment, course_title=canonical.course_title
    )

    structured_dict = structured.model_dump(mode="json")
    canonical_dict = canonical.model_dump(mode="json")

    # 4) Coverage: the structured plan MUST contain exactly the canonical
    #    topics, in canonical order. Refuse to save an incomplete plan.
    coverage = validate_topic_coverage(canonical, structured_dict)
    if not coverage["complete"]:
        raise LessonPlanCoverageError(coverage)

    # Flatten to the backward-compatible newline-delimited topic string.
    lesson_plan_text = structured_to_topic_text(structured)

    # Inherit the course relationship from the parent syllabus, normalized to an
    # ObjectId even if the parent stored course_id as a legacy string.
    course_id = to_object_id(syllabus["course_id"], field="course_id")

    document = create_lesson_plan_document(
        course_id=course_id,
        syllabus_id=syllabus["_id"],
        lesson_plan=lesson_plan_text,
        structured_plan=structured_dict,
        canonical_syllabus=canonical_dict,
        topic_coverage=coverage,
        enrichment=enrichment_status,
    )

    result = await db.lesson_plans.insert_one(document)

    return {
        "lesson_plan_id": str(result.inserted_id),
        "course_id": str(course_id),
        "syllabus_id": str(syllabus["_id"]),
        "lesson_plan": lesson_plan_text,
        "structured_plan": structured_dict,
        "canonical_syllabus": canonical_dict,
        "topic_coverage": coverage,
        "enrichment": enrichment_status,
        "required_hours": canonical.required_hours,
    }


async def delete_lesson_plan(lesson_id: str) -> int:
    """Delete a lesson plan, refusing to orphan dependent records.

    Raises :class:`LessonPlanInUseError` (-> 409) when any generated schedule
    still references the lesson plan via ``lesson_plan_id``. Returns the
    deleted count (0 -> 404) otherwise. A malformed id raises via
    ``to_object_id`` (-> 400), preserving the established endpoint contract.
    """
    db = get_database()
    lesson_oid = to_object_id(lesson_id, field="lesson_id")

    existing = await db.lesson_plans.find_one({"_id": lesson_oid})
    if existing is None:
        return 0

    dependent_schedules = await db.generated_schedules.count_documents(
        {"lesson_plan_id": {"$in": _id_variants(lesson_oid)}}
    )
    if dependent_schedules:
        raise LessonPlanInUseError({"generated schedule(s)": dependent_schedules})

    result = await db.lesson_plans.delete_one({"_id": lesson_oid})
    return result.deleted_count
