"""Progress-monitoring & schedule-deviation orchestration service.

Persistence + auth glue around the pure ``progress_engine``. Nothing here makes
scheduling decisions or calls an LLM; progress is always *derived* from the
sessions already stored inside the active generated-schedule document, so no
duplicate progress state is created (Phase 14).

Responsibilities:
  - locate the active generated schedule for a course
  - update a single session's status in place (Phases 3-5)
  - enforce RBAC ownership (Phase 4)
  - compute progress + deviations via ``progress_engine`` (Phases 6-13)
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from bson import ObjectId

from app.database.mongodb import get_database
from app.models.schedule_model import serialize_schedule
from app.services import progress_engine, scheduler_engine
from app.services.scheduler_engine import (
    WEEKDAYS,
    ScheduleConflictError,
    SchedulerValidationError,
    parse_date,
)
from app.services.scheduler_service import (
    ScheduleNotFoundError,
    _calendar_blocked_dates,
    _calendar_special_days,
    _collect_existing_conflict_sessions,
    _id_variants,
)
from app.utils.object_id import to_object_id
from app.utils.timetable_periods import validate_period_range


class SessionNotFoundError(ScheduleNotFoundError):
    """Raised when the requested session index does not exist (-> 404)."""


class ProgressPermissionError(Exception):
    """Raised when the authenticated user may not edit this schedule (-> 403)."""


def _today() -> date:
    """Reference 'now' for progress math. Isolated so tests can monkeypatch."""
    return datetime.now(UTC).date()


async def _find_active_schedule_document(db, course_oid: ObjectId) -> dict:
    """Return the raw (unserialized) active schedule doc for a course.

    Mirrors ``scheduler_service.get_latest_schedule`` selection logic (active +
    highest version, falling back to newest) but returns the BSON document so
    callers can mutate and persist it.
    """
    schedule = await db.generated_schedules.find_one(
        {"course_id": {"$in": _id_variants(course_oid)}, "active": True},
        sort=[("version", -1)],
    )
    if schedule is None:
        schedule = await db.generated_schedules.find_one(
            {"course_id": {"$in": _id_variants(course_oid)}},
            sort=[("created_at", -1)],
        )
    if schedule is None:
        raise ScheduleNotFoundError("No active schedule found for this course")
    return schedule


async def _resolve_faculty(db, faculty_id):
    """Best-effort lookup of the faculty document referenced by a schedule.

    ``faculty_id`` may be stored as an ObjectId (-> match ``_id``) or as a
    free-form faculty code string (-> match ``faculty_id``). Returns ``None``
    when it cannot be resolved; callers must treat that as "ownership unknown".
    """
    if faculty_id is None:
        return None

    if isinstance(faculty_id, ObjectId):
        return await db.faculty.find_one({"_id": faculty_id})

    faculty = None
    try:
        faculty = await db.faculty.find_one({"_id": ObjectId(str(faculty_id))})
    except Exception:
        faculty = None
    if faculty is None:
        faculty = await db.faculty.find_one({"faculty_id": str(faculty_id)})
    return faculty


async def _is_user_assigned_to_course(db, current_user: dict, course: dict) -> bool:
    """
    Check whether the current user is the assigned faculty (or owner) for a course.
    Used for HOD/Admin users so they can only mutate progress for courses they teach.
    """
    user_email = (current_user.get("email") or "").strip().lower()
    user_id = str(current_user.get("id") or current_user.get("sub") or "")

    # Check direct faculty_id fields on the course document
    for field in ("faculty_id", "assigned_faculty_id"):
        fid = course.get(field)
        if fid:
            faculty = await _resolve_faculty(db, fid)
            f_email = ((faculty or {}).get("email") or "").strip().lower()
            if f_email and user_email and f_email == user_email:
                return True

    # Check array-based faculty_ids
    for fid in (course.get("faculty_ids") or []):
        faculty = await _resolve_faculty(db, fid)
        f_email = ((faculty or {}).get("email") or "").strip().lower()
        if f_email and user_email and f_email == user_email:
            return True

    return False


async def _ensure_can_edit(db, current_user: dict, schedule: dict, course: dict | None = None) -> None:
    """Enforce RBAC ownership for session edits.

    - admin: always permitted (manages the whole system).
    - hod: permitted ONLY when they are assigned/allotted to the course.
           HODs that are not assigned are read-only monitors and may only
           add HOD remarks via the dedicated endpoint.
    - faculty: permitted only when their identity matches the schedule's faculty.
    """
    role = (current_user or {}).get("role")

    if role == "admin":
        return

    if role == "hod":
        # HOD must be assigned to this specific course to modify sessions
        if course and await _is_user_assigned_to_course(db, current_user, course):
            return
        raise ProgressPermissionError(
            "You are not assigned to this course. "
            "HODs may only view progress and add remarks for courses they do not teach."
        )

    if role == "faculty":
        user_email = (current_user.get("email") or "").strip().lower()
        faculty = await _resolve_faculty(db, schedule.get("faculty_id"))
        faculty_email = ((faculty or {}).get("email") or "").strip().lower()
        if user_email and faculty_email and user_email == faculty_email:
            return

    raise ProgressPermissionError(
        "You do not have permission to update sessions for this schedule"
    )


def _attach_session_id(sessions: list[dict]) -> list[dict]:
    """Return sessions with a stable ``session_id`` (+ positional index).

    Sessions generated by the period scheduler carry their own stable
    ``session_id`` (``<topic_id>-sN``) which is preserved. Legacy sessions that
    predate stable ids fall back to their zero-based array position, so old
    schedules keep working unchanged (Task #6 req. 2). ``session_index`` is
    always the array position, letting clients address legacy sessions too.
    """
    enriched = []
    for index, session in enumerate(sessions):
        item = dict(session)
        item["session_id"] = session.get("session_id", index)
        item["session_index"] = index
        enriched.append(item)
    return enriched


def _resolve_session_index(sessions: list[dict], session_id: str) -> int:
    """Map an API ``session_id`` to an array index (Task #6 req. 2).

    Resolution order:
      1. Match a session whose own stable ``session_id`` equals ``session_id``.
      2. Otherwise treat ``session_id`` as a zero-based array index (the legacy
         addressing scheme, preserved for schedules without stable ids).

    Raises ``SessionNotFoundError`` when neither resolves.
    """
    target = str(session_id)
    for index, session in enumerate(sessions):
        if str(session.get("session_id")) == target:
            return index

    try:
        index = int(target)
    except (TypeError, ValueError):
        raise SessionNotFoundError(f"Session '{session_id}' not found")
    if index < 0 or index >= len(sessions):
        raise SessionNotFoundError(f"Session '{session_id}' not found")
    return index


def _weekday_name(d) -> str:
    """Canonical weekday name for a ``date``/``datetime``/ISO string."""
    return WEEKDAYS[parse_date(d, "date").weekday()]


def _is_period_based_session(session: dict) -> bool:
    """A session is period-based when it carries planned period numbers."""
    return session.get("period_start") is not None and session.get("period_end") is not None


def _coerce_actual_hours(actual_hours, planned_hours: float) -> float:
    """Validate/normalize executed hours for a completed session (req. 4/6).

    Rules (kept strictly within the existing domain model):
      * ``actual_hours`` defaults to the planned duration when omitted — a plain
        "mark completed" means "taught as planned".
      * must be a number > 0.
      * must not exceed the planned duration (the domain model does not allow
        teaching more hours than were planned for a session).
    """
    if actual_hours is None:
        return round(float(planned_hours), 2)
    try:
        value = float(actual_hours)
    except (TypeError, ValueError):
        raise SchedulerValidationError("actual_hours must be a number")
    if value <= 0:
        raise SchedulerValidationError("actual_hours must be greater than 0")
    if planned_hours and value > float(planned_hours) + 1e-6:
        raise SchedulerValidationError(
            f"actual_hours ({value}) cannot exceed the planned "
            f"duration ({planned_hours}) for this session"
        )
    return round(value, 2)


def _apply_completion(
    session: dict,
    executed_date: str | None,
    executed_period_start,
    executed_period_end,
    actual_hours,
    actual_topics,
    remarks,
) -> None:
    """Record execution data for a completed session in place (req. 3/5/6).

    Planned fields (``date``/``day``/``period_start``/``period_end``/``topic``…)
    are never touched — they are historical plan data. Execution is stored in a
    parallel set of ``executed_*``/``actual_*`` fields. Defaults assume the
    session was taught as planned when specifics are omitted.
    """
    planned_hours = session.get("duration_hours", 0)

    # Executed date (req. 6): required for completed work; defaults to the
    # planned date so a bare "mark completed" is always valid execution info.
    exec_date = executed_date or session.get("date")
    if not exec_date:
        raise SchedulerValidationError(
            "executed_date is required to complete a session"
        )
    exec_date_iso = parse_date(exec_date, "executed_date").isoformat()
    session["executed_date"] = exec_date_iso
    session["executed_day"] = _weekday_name(exec_date_iso)

    # Executed periods (req. 6): only for period-based schedules. Validate the
    # 1..7 range (lunch has no number, so it can never be selected) and
    # start <= end. Defaults to the planned periods when omitted.
    if _is_period_based_session(session) or executed_period_start is not None:
        p_start = (
            executed_period_start
            if executed_period_start is not None
            else session.get("period_start")
        )
        p_end = (
            executed_period_end
            if executed_period_end is not None
            else session.get("period_end")
        )
        if p_start is not None and p_end is not None:
            try:
                p_start, p_end = validate_period_range(p_start, p_end)
            except ValueError as exc:
                raise SchedulerValidationError(str(exc))
            session["executed_period_start"] = p_start
            session["executed_period_end"] = p_end

    session["actual_hours"] = _coerce_actual_hours(actual_hours, planned_hours)

    if actual_topics is not None:
        # Kept separate from the planned ``topic``/``topic_id`` (req. 5).
        session["actual_topics"] = actual_topics
    if remarks is not None:
        session["faculty_remarks"] = remarks


async def update_session_status(
    course_id: str,
    session_id: str,
    status_value: str,
    actual_date: str | None,
    current_user: dict,
    *,
    executed_date: str | None = None,
    executed_period_start=None,
    executed_period_end=None,
    actual_hours=None,
    actual_topics=None,
    remarks: str | None = None,
) -> dict:
    """Update one session's teaching status + execution data (Task #6 req. 3-6).

    ``session_id`` is either the session's stable ``session_id`` or its
    zero-based array index (legacy addressing). Only that session is modified;
    the original planned fields are preserved and execution is recorded in a
    parallel set of ``executed_*``/``actual_*`` fields.

    Status transitions are validated (req. 4): e.g. a ``completed`` session can
    never silently return to ``pending``. Completing a session records/validates
    executed date, executed periods and actual hours; skipping and the legacy
    ``rescheduled`` path preserve backward-compatible behaviour (the fully
    validated reschedule lives in :func:`reschedule_session`).
    """
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    course = await db.courses.find_one({"_id": course_oid})
    if not course:
        raise ScheduleNotFoundError("Course not found")

    schedule = await _find_active_schedule_document(db, course_oid)
    await _ensure_can_edit(db, current_user, schedule, course)

    sessions = schedule.get("sessions") or []
    index = _resolve_session_index(sessions, session_id)

    session = dict(sessions[index])

    # req. 4: guard against nonsensical status moves before mutating anything.
    current_status = session.get("status")
    if not progress_engine.is_valid_transition(current_status, status_value):
        raise SchedulerValidationError(
            f"Invalid status transition: '{current_status or 'pending'}' -> "
            f"'{status_value}'"
        )

    now = datetime.now(UTC)
    session["status"] = status_value

    if status_value == progress_engine.COMPLETED:
        if not remarks or not remarks.strip():
            raise SchedulerValidationError("Faculty remarks are mandatory when marking a session as complete.")

        _apply_completion(
            session,
            executed_date,
            executed_period_start,
            executed_period_end,
            actual_hours,
            actual_topics,
            remarks,
        )
    else:
        # Non-completion updates never carry executed hours; record optional
        # remarks / actual topics if supplied.
        if actual_topics is not None:
            session["actual_topics"] = actual_topics
        if remarks is not None:
            session["faculty_remarks"] = remarks
        if actual_date:
            # Preserve the original planned date; store the new date separately
            # so a re-dated session never loses its plan (legacy behaviour).
            session["actual_date"] = parse_date(
                actual_date, "actual_date"
            ).isoformat()

    session["updated_at"] = now.isoformat()
    sessions[index] = session

    await db.generated_schedules.update_one(
        {"_id": schedule["_id"]},
        {"$set": {"sessions": sessions, "updated_at": now}},
    )

    try:
        if status_value == progress_engine.COMPLETED:
            from app.services.notification_service import dispatch_targeted_notification, resolve_department_hod
            dept = course.get("department")
            hod_recipients = await resolve_department_hod(dept, exclude_user_id=current_user["id"])
            for hod_uid in hod_recipients:
                await dispatch_targeted_notification(
                    recipient_id=hod_uid,
                    actor_id=current_user["id"],
                    actor_name=current_user.get("name", "Faculty"),
                    event_type="TOPIC_COMPLETED",
                    entity_type="PROGRESS",
                    entity_id=course_id,
                    course_id=course_id,
                    severity="SUCCESS",
                    type="success",
                    title="Topic Completed",
                    message=f"Session topic '{session.get('topic', '')}' for {course.get('course_code', 'Course')} was marked completed by {current_user.get('name')}.",
                    link="/progress",
                    email_subject=f"Topic Completed: {course.get('course_code')}",
                    metadata={
                        "course_code": course.get("course_code"),
                        "topic": session.get("topic"),
                        "completed_by": current_user.get("name"),
                        "remarks": remarks
                    }
                )
    except Exception as e:
        print(f"Failed to dispatch progress notification: {e}")

    session_out = dict(session)
    session_out.setdefault("session_id", index)
    session_out["session_index"] = index
    return {
        "course_id": str(course_oid),
        "schedule_id": str(schedule["_id"]),
        "session": session_out,
    }


async def _load_calendar_for_schedule(db, schedule: dict) -> dict:
    """Load the academic calendar the schedule was generated against."""
    calendar_id = schedule.get("calendar_id")
    calendar = None
    if calendar_id is not None:
        calendar = await db.academic_calendar.find_one(
            {"_id": {"$in": _id_variants(calendar_id)}}
        )
    if calendar is None:
        raise SchedulerValidationError(
            "Cannot reschedule: the schedule's academic calendar is unavailable"
        )
    return calendar


async def _load_timetable_for_schedule(db, schedule: dict) -> dict | None:
    """Load the timetable the schedule was generated against (may be absent)."""
    timetable_id = schedule.get("timetable_id")
    if timetable_id is None:
        return None
    return await db.timetables.find_one({"_id": {"$in": _id_variants(timetable_id)}})


def _validate_reschedule_date(calendar: dict, target):
    """Return the effective weekday if ``target`` is a valid teaching date.

    Reuses the Task #5 calendar rules (blocked holiday/exam/vacation ranges +
    special swap days + working days) so rescheduling can never land on a
    non-teachable date. Raises ``SchedulerValidationError`` otherwise.
    """
    teachable = scheduler_engine.build_teachable_days(
        calendar_model=calendar,
        semester_start=calendar.get("semester_start"),
        semester_end=calendar.get("semester_end"),
    )
    teachable_map = {d: wd for d, wd, _ in teachable}
    if target not in teachable_map:
        raise SchedulerValidationError(
            f"Cannot reschedule to {target.isoformat()}: it is a holiday, exam, "
            "vacation, or non-working day per the academic calendar"
        )
    return teachable_map[target]


def _validate_reschedule_period(
    timetable: dict | None,
    effective_weekday: str,
    period_start,
    period_end,
) -> tuple[int, int]:
    """Validate a rescheduled period against the faculty timetable (req. 7).

    Enforces the 1..7 range and ``start <= end`` (lunch is never a period, so
    it can never be selected), then requires the requested block to fall inside
    an actual timetable slot on the target weekday. Raises
    ``SchedulerValidationError`` for an invalid or unavailable period.
    """
    try:
        start, end = validate_period_range(period_start, period_end)
    except ValueError as exc:
        raise SchedulerValidationError(str(exc))

    schedule_slots = (timetable or {}).get("schedule")
    if not scheduler_engine.timetable_is_period_based(schedule_slots):
        raise SchedulerValidationError(
            "Cannot validate a period reschedule: the faculty timetable is not "
            "period-based"
        )
    period_slots = scheduler_engine.build_period_slots_by_weekday(schedule_slots)
    available = period_slots.get(effective_weekday, [])
    if not any(s <= start and end <= e for s, e in available):
        raise SchedulerValidationError(
            f"Period Hour {start}-{end} is not available on {effective_weekday} "
            "in the faculty timetable"
        )
    return start, end


async def reschedule_session(
    course_id: str,
    session_id: str,
    new_date: str,
    current_user: dict,
    *,
    new_period_start=None,
    new_period_end=None,
    actual_topics=None,
    remarks: str | None = None,
) -> dict:
    """Safely reschedule a single session to another valid slot (req. 7).

    Rescheduling never merely overwrites the planned date. It:
      * preserves the original planned date/period,
      * validates the new date against the academic calendar (rejecting
        holiday/exam/vacation/non-working days -> 422),
      * validates the new period against the faculty timetable (-> 422),
      * detects faculty conflicts against other active schedules and sibling
        sessions (-> 409),
      * stores the new slot in parallel ``rescheduled_*`` fields and sets
        ``status = rescheduled``.

    Unrelated sessions are never modified, and no new schedule version is
    created — a reschedule mutates only the one session in place.
    """
    if not remarks or not remarks.strip():
        raise SchedulerValidationError("A reason/remark is mandatory when rescheduling a session.")

    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    course = await db.courses.find_one({"_id": course_oid})
    if not course:
        raise ScheduleNotFoundError("Course not found")

    schedule = await _find_active_schedule_document(db, course_oid)
    await _ensure_can_edit(db, current_user, schedule, course)

    sessions = schedule.get("sessions") or []
    index = _resolve_session_index(sessions, session_id)
    session = dict(sessions[index])

    if not progress_engine.is_valid_transition(
        session.get("status"), progress_engine.RESCHEDULED
    ):
        raise SchedulerValidationError(
            f"Invalid status transition: '{session.get('status') or 'pending'}' "
            "-> 'rescheduled'"
        )

    target = parse_date(new_date, "rescheduled_date")
    calendar = await _load_calendar_for_schedule(db, schedule)
    effective_weekday = _validate_reschedule_date(calendar, target)

    start = end = None
    if new_period_start is not None or new_period_end is not None:
        timetable = await _load_timetable_for_schedule(db, schedule)
        start, end = _validate_reschedule_period(
            timetable, effective_weekday, new_period_start, new_period_end
        )

    # req. 7: conflict detection against the SAME faculty's other active
    # schedules plus this schedule's sibling sessions (never itself).
    faculty_id = schedule.get("faculty_id") or course.get("faculty_id")
    existing = await _collect_existing_conflict_sessions(db, course_oid, faculty_id)
    for i, sibling in enumerate(sessions):
        if i == index:
            continue
        existing.append(
            {
                "date": sibling.get("date"),
                "period_start": sibling.get("period_start"),
                "period_end": sibling.get("period_end"),
                "start_time": sibling.get("start_time"),
                "end_time": sibling.get("end_time"),
                "reason": "Faculty already teaching this course at that time",
            }
        )

    candidate = {
        "date": target.isoformat(),
        "day": WEEKDAYS[target.weekday()],
        "timetable_day": effective_weekday,
        "topic": session.get("topic"),
        "period_start": start,
        "period_end": end,
    }
    conflicts = scheduler_engine.detect_session_conflicts([candidate], existing)
    if conflicts:
        raise ScheduleConflictError(conflicts)

    now = datetime.now(UTC)
    session["status"] = progress_engine.RESCHEDULED
    session["rescheduled_date"] = target.isoformat()
    session["rescheduled_day"] = WEEKDAYS[target.weekday()]
    # Backward-compatible mirror so existing consumers of ``actual_date`` still
    # see the moved date.
    session["actual_date"] = target.isoformat()
    if start is not None:
        session["rescheduled_period_start"] = start
        session["rescheduled_period_end"] = end
    if actual_topics is not None:
        session["actual_topics"] = actual_topics
    if remarks is not None:
        session["faculty_remarks"] = remarks
    session["updated_at"] = now.isoformat()
    sessions[index] = session

    await db.generated_schedules.update_one(
        {"_id": schedule["_id"]},
        {"$set": {"sessions": sessions, "updated_at": now}},
    )

    session_out = dict(session)
    session_out.setdefault("session_id", index)
    session_out["session_index"] = index
    return {
        "course_id": str(course_oid),
        "schedule_id": str(schedule["_id"]),
        "session": session_out,
    }


async def get_course_progress(course_id: str, current_user: dict | None = None) -> dict:
    """Compute derived progress + deviations for a course (Phase 12).
    
    Returns an `is_assigned` flag so the frontend can decide whether action
    buttons should be shown to HOD/Admin viewers who are not the course teacher.
    """
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    course = await db.courses.find_one({"_id": course_oid})
    if not course:
        raise ScheduleNotFoundError("Course not found")

    schedule = await _find_active_schedule_document(db, course_oid)
    sessions = schedule.get("sessions") or []

    computed = progress_engine.compute_progress(sessions, _today())
    serialized = serialize_schedule(schedule)

    # Determine if the current viewer is assigned/allotted to this course
    is_assigned = True  # Faculty always treated as assigned (already enforced at edit level)
    viewer_role = (current_user or {}).get("role")
    if viewer_role in ("admin", "hod") and current_user:
        is_assigned = await _is_user_assigned_to_course(db, current_user, course)

    return {
        "course_id": str(course_oid),
        "schedule_id": str(schedule["_id"]),
        "version": serialized.get("version"),
        "active": serialized.get("active"),
        "faculty_id": str(schedule.get("faculty_id")) if schedule.get("faculty_id") else None,
        "is_assigned": is_assigned,
        "summary": computed["summary"],
        "units": computed["units"],
        "topics": computed["topics"],
        "deviations": computed["deviations"],
        "sessions": _attach_session_id(sessions),
    }


async def get_available_teaching_dates(course_id: str) -> list[dict]:
    """Calculate all teachable dates from today to the end of the semester,
    including available periods if the faculty has a period-based timetable.
    """
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    # Fetch course to get metadata for strict matching
    course = await db.courses.find_one({"_id": course_oid})
    if not course:
        raise ValueError(f"Course not found: {course_id}")

    # Construct target_subject exactly like generate_schedule does
    target_subject = ",".join(
        filter(
            None,
            [
                course.get("course_name"),
                course.get("short_form"),
                course.get("course_code"),
                course.get("short_name"),
            ]
        )
    )

    schedule = await _find_active_schedule_document(db, course_oid)
    calendar = await _load_calendar_for_schedule(db, schedule)
    timetable = await _load_timetable_for_schedule(db, schedule)

    # Use semester start so faculty can mark past sessions complete
    start_date = parse_date(calendar.get("semester_start"))
    
    end_date_str = calendar.get("last_working_day") or calendar.get("semester_end")
    for event in calendar.get("events", []):
        if event.get("type") == "last_working_day" and event.get("date"):
            end_date_str = event.get("date")
            break
            
    end_date = parse_date(end_date_str)

    # We can use the existing teachable_days function from scheduler_engine
    teachable = scheduler_engine.build_teachable_days(
        calendar_model=calendar,
        semester_start=start_date.isoformat(),
        semester_end=end_date.isoformat(),
    )

    is_period_based = False
    period_slots = {}
    if timetable and timetable.get("schedule"):
        schedule_slots = timetable["schedule"]
        is_period_based = scheduler_engine.timetable_is_period_based(schedule_slots)
        if is_period_based:
            period_slots = scheduler_engine.build_period_slots_by_weekday(
                schedule_slots,
                target_subject=target_subject
            )

    available_dates = []
    for dt, effective_weekday in teachable:
        # If period based, only include days where the faculty actually has periods
        periods = []
        if is_period_based:
            # Flatten tuples like [(1, 2), (3, 3)] into dicts
            for p_start, p_end in period_slots.get(effective_weekday, []):
                # Exclude lab hours (blocks where period spans more than 1 hour)
                if p_start < p_end:
                    continue
                periods.append({"start": p_start, "end": p_end})
            if not periods:
                continue

        available_dates.append({
            "date": dt.isoformat(),
            "weekday": WEEKDAYS[dt.weekday()],
            "effective_weekday": effective_weekday,
            "periods": periods
        })

    return available_dates


async def add_hod_remark(
    course_id: str,
    session_id: str,
    remark: str,
    current_user: dict,
) -> dict:
    """Allow HOD to add a monitoring remark to any session without changing its status.

    This is the HOD's read-only-monitor write action: they can annotate
    sessions with supervisory feedback visible to the assigned faculty.
    The session status is NEVER changed by this function.
    """
    role = (current_user or {}).get("role")
    if role not in ("admin", "hod"):
        raise ProgressPermissionError("Only HOD or Admin can add supervisory remarks.")

    if not remark or not remark.strip():
        raise SchedulerValidationError("Remark cannot be empty.")

    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    course = await db.courses.find_one({"_id": course_oid})
    if not course:
        raise ScheduleNotFoundError("Course not found")

    schedule = await _find_active_schedule_document(db, course_oid)
    sessions = schedule.get("sessions") or []
    index = _resolve_session_index(sessions, session_id)
    session = dict(sessions[index])

    now = datetime.now(UTC)

    # Append to a list of HOD remarks (preserves history)
    hod_remarks = list(session.get("hod_remarks") or [])
    hod_remarks.append({
        "author_id": str(current_user.get("id") or current_user.get("sub") or ""),
        "author_name": current_user.get("name", "HOD"),
        "remark": remark.strip(),
        "created_at": now.isoformat(),
    })
    session["hod_remarks"] = hod_remarks
    session["updated_at"] = now.isoformat()
    sessions[index] = session

    await db.generated_schedules.update_one(
        {"_id": schedule["_id"]},
        {"$set": {"sessions": sessions, "updated_at": now}},
    )

    # Notify the faculty about the HOD's remark
    try:
        from app.services.notification_service import dispatch_targeted_notification, resolve_course_recipients
        recipients = await resolve_course_recipients(course_id, exclude_user_id=str(current_user.get("id") or ""))
        for uid in recipients:
            await dispatch_targeted_notification(
                recipient_id=uid,
                actor_id=str(current_user.get("id") or current_user.get("sub") or ""),
                actor_name=current_user.get("name", "HOD"),
                event_type="HOD_REMARK_ADDED",
                entity_type="PROGRESS",
                entity_id=course_id,
                course_id=course_id,
                severity="INFO",
                type="info",
                title="HOD Feedback on Session Progress",
                message=f"Your HOD left a remark on session '{session.get('topic', '')}' "
                        f"for {course.get('course_code', 'this course')}: \"{remark.strip()[:80]}\"",
                link=f"/progress/{course_id}",
            )
    except Exception:
        pass  # Never block the remark save if notification fails

    return {
        "message": "Remark added successfully",
        "session_id": session_id,
        "hod_remarks": hod_remarks,
    }
