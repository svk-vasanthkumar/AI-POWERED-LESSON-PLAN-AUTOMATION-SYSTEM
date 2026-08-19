from datetime import datetime, UTC

from bson import ObjectId


def create_schedule_document(
    course_id,
    faculty_id,
    lesson_plan_id,
    calendar_id,
    timetable_id,
    sessions: list,
    total_hours: float,
    version: int = 1,
    status: str = "generated",
    academic_year: str | None = None,
    semester=None,
    scheduling_mode: str | None = None,
):
    """Build a generated-schedule document (Phase 10).

    Relationship keys are stored as ObjectIds when they are valid ObjectIds so
    they reference their parent collections natively; otherwise the original
    value is kept as-is (defensive against legacy string ids). ``active`` marks
    the current live schedule for a course so regeneration can supersede an old
    version without deleting it (Phase 13).

    ``academic_year`` / ``semester`` record the calendar context the schedule
    was generated against (the scheduler now selects a calendar by both), and
    ``scheduling_mode`` records whether sessions were laid out on the period
    grid (``"period"``) or legacy clock times (``"clock"``). Each ``session``
    already carries its own ``date``/``day``/``timetable_day`` plus either
    ``period_start``/``period_end`` (and optional clock times) or legacy
    ``start_time``/``end_time``.
    """
    now = datetime.now(UTC)
    return {
        "course_id": _coerce_object_id(course_id),
        "faculty_id": _coerce_object_id(faculty_id),
        "lesson_plan_id": _coerce_object_id(lesson_plan_id),
        "calendar_id": _coerce_object_id(calendar_id),
        "timetable_id": _coerce_object_id(timetable_id),
        "academic_year": academic_year,
        "semester": semester,
        "scheduling_mode": scheduling_mode,
        "sessions": sessions,
        "total_hours": total_hours,
        "version": version,
        "active": True,
        "status": status,
        "created_at": now,
        "updated_at": now,
    }


def _coerce_object_id(value):
    """Return an ObjectId when ``value`` is a valid one, else the value itself."""
    if value is None or isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return value


def serialize_schedule(document: dict) -> dict:
    """Convert a stored schedule document into a JSON-safe dict.

    Stringifies every ObjectId reference and ISO-formats datetimes so the API
    can return it directly without leaking BSON types.
    """
    if not document:
        return document

    result = dict(document)
    for key in (
        "_id",
        "course_id",
        "faculty_id",
        "lesson_plan_id",
        "calendar_id",
        "timetable_id",
    ):
        if key in result and isinstance(result[key], ObjectId):
            result[key] = str(result[key])

    for key in ("created_at", "updated_at"):
        value = result.get(key)
        if isinstance(value, datetime):
            result[key] = value.isoformat()

    return result
