from datetime import datetime, UTC

from bson import ObjectId


def create_lesson_plan_document(
    course_id: ObjectId,
    syllabus_id: ObjectId,
    lesson_plan: str,
    structured_plan: dict | None = None,
):
    """Creates a standardized dictionary structure for MongoDB lesson-plan insertion.

    Stores the relationship keys (``course_id`` / ``syllabus_id`` as ObjectIds),
    the flattened newline-delimited ``lesson_plan`` (kept for backward-compatible
    consumers such as the scheduler), and the validated ``structured_plan`` JSON
    document that the scheduler / frontend can consume directly. The full
    syllabus text is intentionally NOT duplicated here — it lives on the parent
    syllabus document and is reachable via ``syllabus_id``.
    """
    now = datetime.now(UTC)
    return {
        "course_id": course_id,
        "syllabus_id": syllabus_id,
        "lesson_plan": lesson_plan,
        "structured_plan": structured_plan,
        "created_at": now,
        "updated_at": now,
    }
