"""Calendar-aware lesson scheduler service.

Replaces the previous naive "split newlines and map to timetable slots"
behavior with a real, deterministic scheduler that consumes the structured AI
lesson plan and the academic calendar.

Responsibilities handled here (persistence + orchestration):
  - load course / structured lesson plan / calendar / timetable
  - hand plain data to the pure ``scheduler_engine`` for allocation
  - detect conflicts against previously generated schedules
  - persist a versioned schedule and supersede the previous active one
  - compute faculty workload

All scheduling *decisions* live in ``scheduler_engine`` and are fully
deterministic (no LLM involvement).
"""

from __future__ import annotations

from bson import ObjectId

from app.database.mongodb import get_database
from app.models.schedule_model import create_schedule_document, serialize_schedule
from app.services import scheduler_engine
from app.services.scheduler_engine import (
    ScheduleConflictError,
    SchedulerValidationError,
)
from app.utils.calendar_dates import (
    expand_range_dates,
    normalize_blocked_periods,
    normalize_special_days,
    to_date,
)
from app.utils.object_id import to_object_id


class ScheduleNotFoundError(Exception):
    """Raised when a required document (course/plan/calendar/timetable) is missing.

    The API layer maps this to a controlled 404.
    """


def _id_variants(oid) -> list:
    """Return both ObjectId and string forms of an id.

    Different collections in this codebase historically stored relationship
    keys either as ObjectIds (newer writes) or strings (legacy). Querying with
    both forms keeps the scheduler robust without migrating any data.
    """
    return [oid, str(oid)]


async def _find_course(db, course_oid: ObjectId) -> dict:
    course = await db.courses.find_one({"_id": course_oid})
    if not course:
        raise ScheduleNotFoundError("Course not found")
    return course


async def _find_structured_lesson_plan(db, course_oid: ObjectId) -> dict:
    """Locate the most relevant lesson plan for a course.

    Resolves the plan via the course's syllabus (the canonical relationship)
    and falls back to a direct ``course_id`` match. Prefers the newest document.
    """
    # Primary path: course -> syllabus -> lesson plan.
    syllabus = await db.syllabi.find_one(
        {"course_id": {"$in": _id_variants(course_oid)}}
    )
    lesson = None
    if syllabus:
        lesson = await db.lesson_plans.find_one(
            {"syllabus_id": {"$in": _id_variants(syllabus["_id"])}},
            sort=[("created_at", -1)],
        )
    if lesson is None:
        lesson = await db.lesson_plans.find_one(
            {"course_id": {"$in": _id_variants(course_oid)}},
            sort=[("created_at", -1)],
        )
    if lesson is None:
        raise ScheduleNotFoundError("Lesson plan not found")
    return lesson


async def _resolve_academic_year(course: dict, timetable: dict, academic_year):
    """Resolve the academic-year context used to pick the calendar (req. 1).

    Priority: an explicit ``academic_year`` argument (e.g. a request query
    param) > the course's own ``academic_year`` field > the timetable's
    ``academic_year`` field. Returns ``None`` when no context exists anywhere
    (older data that never stored an academic year).
    """
    for candidate in (
        academic_year,
        course.get("academic_year"),
        (timetable or {}).get("academic_year"),
    ):
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return None


async def _find_calendar(db, course: dict, timetable: dict, academic_year=None, calendar_id: str | None = None) -> dict:
    """Find the academic calendar for BOTH academic_year and semester (req. 1).

    The scheduler must never select a calendar by semester alone when an
    academic-year context is available, and must never silently pick the wrong
    academic year:

      * When an academic year is known, the calendar is matched on
        ``(academic_year, semester)`` exactly. A miss is a controlled 404.
      * When no academic-year context exists anywhere (legacy data), we look at
        every calendar for the semester. If they span more than one academic
        year the selection is ambiguous and we fail with a controlled 422 (so
        the caller must supply ``academic_year``) rather than guess. A single
        unambiguous calendar is used for backward compatibility.
    """
    if calendar_id:
        calendar_oid = to_object_id(calendar_id, field="calendar_id")
        calendar = await db.academic_calendar.find_one({"_id": calendar_oid})
        if not calendar:
            raise ScheduleNotFoundError("Explicitly selected academic calendar not found")
        return calendar

    semester = course.get("semester")
    resolved_year = await _resolve_academic_year(course, timetable, academic_year)

    if resolved_year is not None:
        calendar = await db.academic_calendar.find_one(
            {"academic_year": resolved_year, "semester": semester},
            sort=[("created_at", -1)],
        )
        if calendar is None:
            raise ScheduleNotFoundError(
                f"Academic calendar not found for academic year "
                f"'{resolved_year}', semester {semester}"
            )
        return calendar

    # No academic-year context anywhere — inspect all calendars for the semester.
    calendars = [
        doc
        async for doc in db.academic_calendar.find({"semester": semester}).sort(
            "created_at", -1
        )
    ]
    if not calendars:
        raise ScheduleNotFoundError("Academic calendar not found")

    distinct_years = {
        c.get("academic_year") for c in calendars if c.get("academic_year") is not None
    }
    if len(distinct_years) > 1:
        raise SchedulerValidationError(
            "Multiple academic calendars exist for semester "
            f"{semester} across academic years {sorted(distinct_years)}. "
            "Specify the academic year to select the correct calendar."
        )
    return calendars[0]


async def _find_timetable(db, course_oid: ObjectId, timetable_id: str | None = None) -> dict:
    if timetable_id:
        timetable_oid = to_object_id(timetable_id, field="timetable_id")
        timetable = await db.timetables.find_one({"_id": timetable_oid})
        if not timetable:
            raise ScheduleNotFoundError("Explicitly selected timetable not found")
        return timetable

    timetable = await db.timetables.find_one(
        {"course_id": {"$in": _id_variants(course_oid)}},
        sort=[("created_at", -1)],
    )
    if timetable is None:
        raise ScheduleNotFoundError("Timetable not found")
    return timetable


async def _collect_existing_conflict_sessions(
    db,
    course_oid: ObjectId,
    faculty_id,
) -> list[dict]:
    """Gather sessions from other active schedules that could conflict (Phase 8).

    A conflict is any active schedule for the SAME faculty (on a different
    course). The current course's own schedules are excluded because they will
    be superseded, not conflicted with.
    """
    faculty_variants = []
    if faculty_id is not None:
        faculty_variants = (
            _id_variants(faculty_id)
            if isinstance(faculty_id, ObjectId)
            else [faculty_id, str(faculty_id)]
        )

    if not faculty_variants:
        return []

    query = {
        "active": True,
        "faculty_id": {"$in": faculty_variants},
        "course_id": {"$nin": _id_variants(course_oid)},
    }

    existing_sessions: list[dict] = []
    async for schedule in db.generated_schedules.find(query):
        for session in schedule.get("sessions", []):
            existing_sessions.append(
                {
                    "date": session.get("date"),
                    "day": session.get("day"),
                    "timetable_day": session.get("timetable_day"),
                    # Period-based comparison (new timetables) …
                    "period_start": session.get("period_start"),
                    "period_end": session.get("period_end"),
                    # … and clock-time comparison (legacy timetables).
                    "start_time": session.get("start_time"),
                    "end_time": session.get("end_time"),
                    "reason": "Faculty already teaching another course",
                }
            )
    return existing_sessions


def _validate_faculty_relationship(course: dict, timetable: dict) -> None:
    """Reject a timetable whose faculty does not match the course (req. 9).

    Both ids are compared as strings so an ObjectId reference and its string
    form are treated as equal. When either side has no faculty recorded the
    check is skipped (nothing to contradict).
    """
    course_faculty = course.get("faculty_id")
    timetable_faculty = timetable.get("faculty_id")
    if course_faculty is None or timetable_faculty is None:
        return
    if str(course_faculty) != str(timetable_faculty):
        raise SchedulerValidationError(
            "Timetable faculty does not match the course's assigned faculty"
        )


def _calendar_blocked_dates(calendar: dict) -> set:
    """Collect every non-teachable date from a calendar document (req. 2).

    Unions, into a single ``set[date]``:
      * holidays (new ``{date, name}`` dicts OR legacy plain date strings),
      * the flattened legacy ``internal_exams`` list,
      * every date inside the structured exam ranges (CIA I/II/III, model
        practical/theory, semester-end practical/theory), winter vacation and
        any other ``blocked_periods`` — expanded via the calendar utilities.

    No dates are hard-coded; everything comes from the stored calendar.
    """
    blocked: set = set()

    try:
        for holiday in calendar.get("holidays") or []:
            raw = holiday.get("date") if isinstance(holiday, dict) else holiday
            blocked.add(to_date(raw))

        for raw in calendar.get("internal_exams") or []:
            blocked.add(to_date(raw))

        for period in normalize_blocked_periods(calendar):
            for day in expand_range_dates(period["start_date"], period["end_date"]):
                blocked.add(day)

        # New calendar ingestion stores events uniformly instead of maintaining
        # one field per exam type. Block only events that actually prevent
        # teaching; registration/report/notification milestones do not block a
        # timetable day.
        blocking_types = {
            "cia",
            "cia_report",
            "model_practical",
            "model_theory",
            "remedial",
            "semester_end_practical",
            "semester_end_theory",
            "hall_ticket",
            "ia_report",
            "winter_vacation",
        }
        for event in calendar.get("events") or []:
            if not isinstance(event, dict) or event.get("type") not in blocking_types:
                continue
            if event.get("start_date") and event.get("end_date"):
                for day in expand_range_dates(
                    to_date(event["start_date"]),
                    to_date(event["end_date"]),
                ):
                    blocked.add(day)
            elif event.get("date"):
                blocked.add(to_date(event["date"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise SchedulerValidationError(
            f"Invalid academic calendar data: {exc}"
        )

    return blocked


def _calendar_special_days(calendar: dict) -> list[dict]:
    """Return ``[{date, timetable_day}]`` swap entries for a calendar (req. 3)."""
    try:
        return normalize_special_days(calendar)
    except (ValueError, KeyError, TypeError) as exc:
        raise SchedulerValidationError(
            f"Invalid special timetable day in calendar: {exc}"
        )


# Execution fields carried forward from a superseded schedule onto a matching
# freshly-generated session (Task #6 req. 11). Planned fields are never copied.
_EXECUTION_CARRY_FIELDS = (
    "status",
    "executed_date",
    "executed_day",
    "executed_period_start",
    "executed_period_end",
    "actual_hours",
    "actual_topics",
    "faculty_remarks",
    "actual_date",
    "rescheduled_date",
    "rescheduled_day",
    "rescheduled_period_start",
    "rescheduled_period_end",
    "updated_at",
)


def _carry_forward_execution(
    new_sessions: list[dict],
    previous_sessions: list[dict],
) -> int:
    """Carry recorded execution from a superseded schedule into a new one.

    Matching rule (deliberately strict — never guess, Task #6 req. 11): a new
    session inherits a previous session's execution ONLY when all of the
    following match exactly, so the topic and its planned chunk are provably the
    same piece of work:

        * stable ``session_id`` (``<topic_id>-sN``), AND
        * ``topic_id``, AND
        * ``topic`` text, AND
        * planned ``duration_hours``.

    When a previous session had real execution history (status in
    completed/skipped/rescheduled) and matches, its execution fields are copied
    onto the new session. Anything that cannot be matched this way is left as a
    fresh ``pending`` session. Returns the number of sessions carried forward.
    """
    if not previous_sessions:
        return 0

    index: dict[tuple, dict] = {}
    for prev in previous_sessions:
        status = prev.get("status")
        if status in (None, "pending"):
            continue  # no execution history worth preserving
        key = (
            prev.get("session_id"),
            prev.get("topic_id"),
            prev.get("topic"),
            prev.get("duration_hours"),
        )
        if key[0] is None:
            continue  # legacy session without a stable id -> cannot match safely
        index[key] = prev

    carried = 0
    for session in new_sessions:
        key = (
            session.get("session_id"),
            session.get("topic_id"),
            session.get("topic"),
            session.get("duration_hours"),
        )
        prev = index.get(key)
        if prev is None:
            continue
        for field in _EXECUTION_CARRY_FIELDS:
            if field in prev:
                session[field] = prev[field]
        carried += 1
    return carried


async def generate_schedule(
    course_id: str, 
    academic_year: str | None = None,
    calendar_id: str | None = None,
    timetable_id: str | None = None,
) -> dict:
    """Generate (or regenerate) a conflict-free schedule for a course.

    Consumes the new academic calendar (blocked ranges + special/swap days) and
    the period-based faculty timetable (Hour 1..7 with lunch and multi-period
    lab blocks), while still supporting legacy clock-time timetables.

    Args:
        course_id: the course whose schedule to (re)generate.
        academic_year: optional academic-year context used to select the
            correct calendar (req. 1). When omitted it is resolved from the
            course/timetable, falling back to an unambiguous single calendar.

    Raises:
        HTTPException(400): malformed ``course_id`` (via ``to_object_id``).
        ScheduleNotFoundError: a required document is missing (-> 404).
        SchedulerValidationError: bad calendar/timetable/plan data, an
            academic-year ambiguity, or a faculty mismatch (-> 422).
        ScheduleConflictError: overlaps with existing schedules (-> 409). Raised
            BEFORE anything is persisted, so no partial schedule is ever stored.
    """
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    course = await _find_course(db, course_oid)
    lesson = await _find_structured_lesson_plan(db, course_oid)
    timetable = await _find_timetable(db, course_oid, timetable_id)
    calendar = await _find_calendar(db, course, timetable, academic_year, calendar_id)

    # req. 9: the timetable's faculty must match the course's assigned faculty.
    _validate_faculty_relationship(course, timetable)

    # req. (topics): require the structured plan; never parse the flat text.
    topics = scheduler_engine.extract_topics(lesson.get("structured_plan"))

    # req. 2-3: the single "is this date teachable?" mechanism, with special /
    # swap timetable days resolving each teachable date's effective weekday.
    teachable_days = scheduler_engine.build_teachable_days(
        calendar.get("semester_start"),
        calendar.get("semester_end"),
        calendar.get("working_days"),
        blocked_dates=_calendar_blocked_dates(calendar),
        special_days=_calendar_special_days(calendar),
    )

    schedule_slots = timetable.get("schedule")

    # req. 4-6 + 12: pick the period engine for period-based timetables, and the
    # legacy clock-time engine for old clock-time timetables. Period times are
    # attached only when configured (never invented).
    if scheduler_engine.timetable_is_period_based(schedule_slots):
        period_slots = scheduler_engine.build_period_slots_by_weekday(schedule_slots)
        period_time_map = scheduler_engine.build_period_time_map_by_weekday(
            schedule_slots
        )
        blocks = scheduler_engine.build_period_blocks(
            teachable_days,
            period_slots,
            period_time_map=period_time_map,
        )
        scheduling_mode = "period"
    else:
        clock_slots = scheduler_engine.build_slots_by_weekday(schedule_slots)
        blocks = scheduler_engine.build_clock_blocks(teachable_days, clock_slots)
        scheduling_mode = "clock"

    # req. 10: allocate topic hours across blocks in deterministic unit/topic
    # order; topics that do not fit before semester end are reported.
    sessions, unscheduled = scheduler_engine.allocate_blocks(topics, blocks)

    for topic in topics:
        topic_id = topic["topic_id"]
        requested = float(topic["estimated_hours"])
        scheduled = sum(
            float(session.get("duration_hours", 0))
            for session in sessions
            if session.get("topic_id") == topic_id
        )

        if scheduled - requested > 1e-6:
            raise SchedulerValidationError(
                f"Scheduler over-allocated topic '{topic_id}'"
            )

    # The faculty owning this schedule comes from the timetable (its faculty_id
    # reflects who teaches these slots); fall back to the course's faculty_id.
    faculty_id = timetable.get("faculty_id") or course.get("faculty_id")

    # req. 8: conflict detection against existing active schedules of the SAME
    # faculty, on the same date + effective period. Fail before persisting.
    existing_sessions = await _collect_existing_conflict_sessions(
        db, course_oid, faculty_id
    )
    conflicts = scheduler_engine.detect_session_conflicts(sessions, existing_sessions)
    if conflicts:
        raise ScheduleConflictError(conflicts)

    total_hours = scheduler_engine.calculate_total_hours(sessions)

    # req. 11: supersede the previous active version for THIS course without
    # deleting it or touching unrelated schedules.
    previous = await db.generated_schedules.find_one(
        {"course_id": {"$in": _id_variants(course_oid)}, "active": True},
        sort=[("version", -1)],
    )
    next_version = (
        int(previous.get("version") or 0) + 1
        if previous
        else 1
    )
    if previous:
        # req. 11: preserve completed/skipped/rescheduled execution history by
        # carrying it onto reliably-matched new sessions before superseding the
        # old version. Old versions are never mutated, only marked inactive.
        _carry_forward_execution(sessions, previous.get("sessions") or [])
        await db.generated_schedules.update_many(
            {"course_id": {"$in": _id_variants(course_oid)}, "active": True},
            {"$set": {"active": False, "status": "superseded"}},
        )

    document = create_schedule_document(
        course_id=course_oid,
        faculty_id=faculty_id,
        lesson_plan_id=lesson["_id"],
        calendar_id=calendar["_id"],
        timetable_id=timetable["_id"],
        sessions=sessions,
        total_hours=total_hours,
        version=next_version,
        academic_year=calendar.get("academic_year"),
        semester=course.get("semester"),
        scheduling_mode=scheduling_mode,
    )
    result = await db.generated_schedules.insert_one(document)
    document["_id"] = result.inserted_id

    payload = serialize_schedule(document)
    payload["workload"] = {
        "faculty_id": str(faculty_id) if faculty_id is not None else None,
        "total_hours": total_hours,
    }
    if unscheduled:
        # Not an error: the semester window ran out before all topics fit.
        payload["unscheduled_topics"] = unscheduled
    return payload


async def get_latest_schedule(course_id: str) -> dict:
    """Return the latest active generated schedule for a course (Phase 12)."""
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    schedule = await db.generated_schedules.find_one(
        {"course_id": {"$in": _id_variants(course_oid)}, "active": True},
        sort=[("version", -1)],
    )
    if schedule is None:
        # Fall back to the newest schedule regardless of active flag.
        schedule = await db.generated_schedules.find_one(
            {"course_id": {"$in": _id_variants(course_oid)}},
            sort=[("created_at", -1)],
        )
    if schedule is None:
        raise ScheduleNotFoundError("No schedule found for this course")

    return serialize_schedule(schedule)