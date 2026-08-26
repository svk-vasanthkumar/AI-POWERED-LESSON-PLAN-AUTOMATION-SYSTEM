from datetime import datetime, UTC

from bson import ObjectId


def create_lesson_plan_document(
    course_id: ObjectId,
    syllabus_id: ObjectId,
    lesson_plan: str,
    structured_plan: dict | None = None,
    canonical_syllabus: dict | None = None,
    topic_coverage: dict | None = None,
    enrichment: dict | None = None,
):
    """Creates a standardized dictionary structure for MongoDB lesson-plan insertion.

    Stores the relationship keys (``course_id`` / ``syllabus_id`` as ObjectIds),
    the flattened newline-delimited ``lesson_plan`` (kept for backward-compatible
    consumers such as the scheduler), and the validated ``structured_plan`` JSON
    document that the scheduler / frontend can consume directly. The full
    syllabus text is intentionally NOT duplicated here — it lives on the parent
    syllabus document and is reachable via ``syllabus_id``.

    Three provenance fields make the plan auditable:

    ``canonical_syllabus``
        The deterministic parse of the syllabus document (units, ordered topics,
        official hours with their ``hours_source``, outcomes, textbooks). This is
        the authoritative structure that ``structured_plan`` was built from, so a
        later reader can always tell syllabus facts apart from AI additions.
    ``topic_coverage``
        The validation report proving the structured plan contains exactly the
        canonical topics, in canonical order.
    ``enrichment``
        Status of the AI pedagogy pass (``ok`` / ``failed`` plus a safe reason).
        A failed pass still yields a complete, schedulable plan — only the
        pedagogy fields stay empty.
    """
    now = datetime.now(UTC)
    return {
        "course_id": course_id,
        "syllabus_id": syllabus_id,
        "lesson_plan": lesson_plan,
        "structured_plan": structured_plan,
        "canonical_syllabus": canonical_syllabus,
        "topic_coverage": topic_coverage,
        "enrichment": enrichment,
        "created_at": now,
        "updated_at": now,
    }
