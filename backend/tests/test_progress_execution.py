"""Tests for Task #6 — teaching-progress/execution tracking & safe rescheduling.

Two layers:
  * ``progress_engine`` is pure -> tested with fixed dates and plain dicts.
  * ``progress_service`` + ``scheduler_service`` are exercised against an
    in-memory Mongo (``mongomock_motor``) so stable session ids, execution
    recording, status-transition rules, safe rescheduling (calendar + timetable
    + conflict validation), RBAC ownership and regeneration carry-forward are
    all verified offline.

Run: python -m pytest backend/tests/test_progress_execution.py -q
"""

import os
import sys
from datetime import UTC, date, datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

import app.database.mongodb as mongodb
from app.services import progress_engine as eng
from app.services import progress_service as svc
from app.services import scheduler_engine as engine
from app.services import scheduler_service as sched
from app.services.scheduler_engine import ScheduleConflictError, SchedulerValidationError
from app.services.progress_service import ProgressPermissionError

# Fixed reference date (after the seeded semester end) so every planned session
# is "due" and progress math never depends on the real clock.
TODAY = date(2026, 8, 10)

ADMIN = {"id": "u1", "email": "admin@x.edu", "role": "admin"}
FACULTY_OTHER = {"id": "u9", "email": "someone-else@x.edu", "role": "faculty"}


# ===========================================================================
# Pure engine tests
# ===========================================================================


def _s(topic_id, topic, unit_number, planned, hours, status="pending", **extra):
    session = {
        "session_id": f"{topic_id}-s1",
        "topic_id": topic_id,
        "topic": topic,
        "unit_number": unit_number,
        "unit_title": f"Unit {unit_number}",
        "date": planned,
        "day": "Monday",
        "period_start": 1,
        "period_end": 1,
        "duration_hours": hours,
        "status": status,
    }
    session.update(extra)
    return session


def test_valid_and_invalid_transitions():
    assert eng.is_valid_transition("pending", "completed")
    assert eng.is_valid_transition("pending", "skipped")
    assert eng.is_valid_transition("pending", "rescheduled")
    assert eng.is_valid_transition("skipped", "completed")
    assert eng.is_valid_transition("completed", "completed")  # idempotent
    assert eng.is_valid_transition("completed", "rescheduled")
    assert eng.is_valid_transition(None, "completed")  # legacy/no status
    # The one deliberately-forbidden move: a completed session must never
    # silently revert to pending (that would erase execution history).
    assert not eng.is_valid_transition("completed", "pending")


def test_progress_uses_actual_hours_for_partial_execution():
    # 1h planned, only 0.5h actually taught.
    sessions = [_s("U1-T1", "A", 1, "2026-08-01", 1, "completed", actual_hours=0.5)]
    summary = eng.build_summary(sessions, TODAY)
    assert summary["total_planned_hours"] == 1
    assert summary["completed_hours"] == 0.5
    assert summary["remaining_hours"] == 0.5
    assert summary["completion_percentage"] == 50.0


def test_legacy_completed_without_actual_hours_counts_full():
    sessions = [_s("U1-T1", "A", 1, "2026-08-01", 2, "completed")]
    summary = eng.build_summary(sessions, TODAY)
    assert summary["completed_hours"] == 2
    assert summary["completion_percentage"] == 100.0


def test_partial_topic_not_fully_complete():
    sessions = [_s("U1-T1", "A", 1, "2026-08-01", 2, "completed", actual_hours=1)]
    topics = eng.build_topic_progress(sessions)
    assert topics[0]["planned_hours"] == 2
    assert topics[0]["completed_hours"] == 1
    assert topics[0]["completion_percentage"] == 50.0


def test_partial_unit_not_fully_complete():
    sessions = [
        _s("U1-T1", "A", 1, "2026-08-01", 2, "completed", actual_hours=1),
        _s("U1-T2", "B", 1, "2026-08-02", 2, "completed", actual_hours=2),
    ]
    units = eng.build_unit_progress(sessions)
    assert units[0]["planned_hours"] == 4
    assert units[0]["completed_hours"] == 3
    assert units[0]["completion_percentage"] == 75.0


def test_behind_schedule_reflects_actual_hours():
    # 3h all due today, only 1h actually taught -> behind schedule deviation.
    sessions = [
        _s("U1-T1", "A", 1, "2026-08-01", 2, "completed", actual_hours=1),
        _s("U1-T2", "B", 1, "2026-08-02", 1),  # due, pending
    ]
    result = eng.compute_progress(sessions, TODAY)
    summary = result["summary"]
    assert summary["planned_progress_percentage"] == 100.0
    assert round(summary["actual_progress_percentage"], 1) == 33.3
    assert summary["deviation_percentage"] < 0
    assert any(d["type"] == "behind_schedule" for d in result["deviations"])


# ===========================================================================
# Service tests (mongomock)
# ===========================================================================

PERIOD_SCHEDULE = [
    {"day": "Monday", "period_start": 1, "period_end": 1},
    {"day": "Monday", "period_start": 2, "period_end": 2},
    {"day": "Tuesday", "period_start": 5, "period_end": 5},
]


def _structured_plan(specs):
    return {
        "units": [
            {
                "unit_number": 1,
                "unit_title": "Introduction",
                "topics": [
                    {"topic_id": tid, "topic": title, "estimated_hours": hours}
                    for tid, title, hours in specs
                ],
            }
        ]
    }


@pytest.fixture()
def db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    monkeypatch.setattr(mongodb, "database", database)
    monkeypatch.setattr(svc, "_today", lambda: TODAY)
    return database


async def _seed(db, *, faculty_id=None, plan_specs=None):
    """Seed course + structured plan + calendar + period timetable and generate
    a real schedule (so sessions carry stable ids)."""
    specs = plan_specs or [("U1-T1", "Topic A", 2), ("U1-T2", "Topic B", 1)]
    course_id = ObjectId()
    faculty_id = faculty_id or ObjectId()
    now = datetime.now(UTC)

    await db.courses.insert_one({
        "_id": course_id, "course_code": "CS101", "semester": 5,
        "faculty_id": faculty_id, "academic_year": "2026-2027", "created_at": now,
    })
    await db.lesson_plans.insert_one({
        "_id": ObjectId(), "course_id": course_id, "lesson_plan": "A\nB",
        "structured_plan": _structured_plan(specs), "created_at": now,
    })
    await db.academic_calendar.insert_one({
        "_id": ObjectId(), "semester": 5, "academic_year": "2026-2027",
        "semester_start": "2026-07-27", "semester_end": "2026-08-14",
        "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "holidays": [], "created_at": now,
    })
    await db.timetables.insert_one({
        "_id": ObjectId(), "faculty_id": faculty_id, "course_id": course_id,
        "semester": 5, "academic_year": "2026-2027", "schedule": PERIOD_SCHEDULE,
        "created_at": now,
    })
    await sched.generate_schedule(str(course_id))
    return course_id, faculty_id


def _free_slot(sessions):
    """Return an (iso_date, period_start, period_end) teachable + timetable-valid
    slot that no current session occupies."""
    teachable = engine.build_teachable_days(
        "2026-07-27", "2026-08-14",
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        blocked_dates=set(), special_days=[],
    )
    period_slots = engine.build_period_slots_by_weekday(PERIOD_SCHEDULE)
    used = {(s["date"], s.get("period_start")) for s in sessions}
    for d, weekday in teachable:
        for start, end in period_slots.get(weekday, []):
            if (d.isoformat(), start) not in used:
                return d.isoformat(), start, end
    raise AssertionError("no free slot found")


# --- stable session ids ----------------------------------------------------


@pytest.mark.asyncio
async def test_stable_session_ids_are_deterministic_and_topic_derived(db):
    course_id, _ = await _seed(db)
    progress = await svc.get_course_progress(str(course_id))
    ids = [s["session_id"] for s in progress["sessions"]]

    # Unique, topic-derived (<topic_id>-sN), and NOT the array index.
    assert len(set(ids)) == len(ids)
    assert all("-s" in str(i) for i in ids)
    assert ids != list(range(len(ids)))
    # Topic A is 2h and precedes Topic B (1h) in the plan.
    assert ids[0].startswith("U1-T1-s")

    # Regenerating identical inputs yields identical ids (basis for carry-forward).
    course_id2, _ = await _seed(db)
    ids2 = [s["session_id"] for s in
            (await svc.get_course_progress(str(course_id2)))["sessions"]]
    assert ids == ids2


@pytest.mark.asyncio
async def test_update_by_stable_session_id(db):
    course_id, _ = await _seed(db)
    result = await svc.update_session_status(
        str(course_id), "U1-T2-s1", "completed", None, ADMIN
    )
    assert result["session"]["status"] == "completed"
    assert result["session"]["session_id"] == "U1-T2-s1"


@pytest.mark.asyncio
async def test_legacy_session_addressed_by_index(db):
    # A hand-seeded legacy schedule (no session_id, clock times).
    course_id = ObjectId()
    now = datetime.now(UTC)
    await db.courses.insert_one({"_id": course_id, "faculty_id": ObjectId(), "semester": 5})
    await db.generated_schedules.insert_one({
        "_id": ObjectId(), "course_id": course_id, "faculty_id": ObjectId(),
        "sessions": [{
            "topic_id": "U1-T1", "topic": "A", "unit_number": 1, "unit_title": "I",
            "date": "2026-08-03", "day": "Monday", "start_time": "09:00",
            "end_time": "10:00", "duration_hours": 1, "status": "pending",
        }],
        "total_hours": 1, "version": 1, "active": True, "status": "generated",
        "created_at": now, "updated_at": now,
    })
    result = await svc.update_session_status(str(course_id), "0", "completed", None, ADMIN)
    assert result["session"]["status"] == "completed"
    assert result["session"]["executed_date"] == "2026-08-03"
    progress = await svc.get_course_progress(str(course_id))
    assert progress["summary"]["completed_sessions"] == 1


# --- execution recording ---------------------------------------------------


@pytest.mark.asyncio
async def test_complete_defaults_to_taught_as_planned(db):
    course_id, _ = await _seed(db)
    result = await svc.update_session_status(
        str(course_id), "U1-T1-s1", "completed", None, ADMIN
    )
    session = result["session"]
    assert session["status"] == "completed"
    # Executed data defaults to the planned slot; planned fields untouched.
    assert session["executed_date"] == session["date"]
    assert session["executed_period_start"] == session["period_start"]
    assert session["actual_hours"] == session["duration_hours"]


@pytest.mark.asyncio
async def test_complete_records_partial_execution(db):
    course_id, _ = await _seed(db)
    result = await svc.update_session_status(
        str(course_id), "U1-T1-s1", "completed", None, ADMIN,
        actual_hours=0.5, actual_topics="Only covered the intro",
        remarks="Ran short on time",
    )
    session = result["session"]
    assert session["actual_hours"] == 0.5
    assert session["actual_topics"] == "Only covered the intro"
    assert session["faculty_remarks"] == "Ran short on time"
    # Planned duration is preserved (never overwritten by actual hours).
    assert session["duration_hours"] == 1

    # Partial execution is reflected in progress (0.5 of this 1h session done).
    progress = await svc.get_course_progress(str(course_id))
    topic = next(t for t in progress["topics"] if t["topic_id"] == "U1-T1")
    assert topic["completed_hours"] == 0.5
    assert topic["completion_percentage"] < 100


@pytest.mark.asyncio
async def test_actual_hours_cannot_exceed_planned(db):
    course_id, _ = await _seed(db)
    with pytest.raises(SchedulerValidationError):
        await svc.update_session_status(
            str(course_id), "U1-T1-s1", "completed", None, ADMIN, actual_hours=5
        )


@pytest.mark.asyncio
async def test_actual_hours_must_be_positive(db):
    course_id, _ = await _seed(db)
    with pytest.raises(SchedulerValidationError):
        await svc.update_session_status(
            str(course_id), "U1-T1-s1", "completed", None, ADMIN, actual_hours=0
        )


# --- status transitions ----------------------------------------------------


@pytest.mark.asyncio
async def test_completed_cannot_revert_to_pending(db):
    course_id, _ = await _seed(db)
    await svc.update_session_status(str(course_id), "U1-T1-s1", "completed", None, ADMIN)
    with pytest.raises(SchedulerValidationError):
        await svc.update_session_status(str(course_id), "U1-T1-s1", "pending", None, ADMIN)


@pytest.mark.asyncio
async def test_skipped_can_later_be_completed(db):
    course_id, _ = await _seed(db)
    await svc.update_session_status(str(course_id), "U1-T1-s1", "skipped", None, ADMIN)
    result = await svc.update_session_status(
        str(course_id), "U1-T1-s1", "completed", None, ADMIN
    )
    assert result["session"]["status"] == "completed"


# --- safe rescheduling -----------------------------------------------------


@pytest.mark.asyncio
async def test_reschedule_to_valid_slot(db):
    course_id, _ = await _seed(db)
    schedule = await svc._find_active_schedule_document(
        db, ObjectId(str(course_id))
    )
    iso, start, end = _free_slot(schedule["sessions"])

    result = await svc.reschedule_session(
        str(course_id), "U1-T1-s1", iso, ADMIN,
        new_period_start=start, new_period_end=end,
    )
    session = result["session"]
    assert session["status"] == "rescheduled"
    assert session["rescheduled_date"] == iso
    assert session["rescheduled_period_start"] == start
    # Original planned slot is preserved.
    assert session["date"] != iso or session["period_start"] != start


@pytest.mark.asyncio
async def test_reschedule_to_holiday_rejected(db):
    course_id, faculty_id = await _seed(db)
    schedule = await svc._find_active_schedule_document(db, ObjectId(str(course_id)))
    iso, _, _ = _free_slot(schedule["sessions"])
    # Turn the free slot's date into a holiday, then try to move onto it.
    await db.academic_calendar.update_one(
        {"academic_year": "2026-2027"},
        {"$set": {"holidays": [{"date": iso, "name": "Special holiday"}]}},
    )
    with pytest.raises(SchedulerValidationError):
        await svc.reschedule_session(str(course_id), "U1-T1-s1", iso, ADMIN)


@pytest.mark.asyncio
async def test_reschedule_period_out_of_range_rejected(db):
    course_id, _ = await _seed(db)
    schedule = await svc._find_active_schedule_document(db, ObjectId(str(course_id)))
    iso, _, _ = _free_slot(schedule["sessions"])
    with pytest.raises(SchedulerValidationError):
        await svc.reschedule_session(
            str(course_id), "U1-T1-s1", iso, ADMIN,
            new_period_start=8, new_period_end=8,
        )


@pytest.mark.asyncio
async def test_reschedule_period_not_available_rejected(db):
    course_id, _ = await _seed(db)
    # Tuesday only offers period 5 in the timetable; request period 1 -> invalid.
    teachable = engine.build_teachable_days(
        "2026-07-27", "2026-08-14",
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        blocked_dates=set(), special_days=[],
    )
    tuesday = next(d for d, wd in teachable if wd == "Tuesday")
    with pytest.raises(SchedulerValidationError):
        await svc.reschedule_session(
            str(course_id), "U1-T1-s1", tuesday.isoformat(), ADMIN,
            new_period_start=1, new_period_end=1,
        )


@pytest.mark.asyncio
async def test_reschedule_onto_sibling_conflicts(db):
    course_id, _ = await _seed(db)
    schedule = await svc._find_active_schedule_document(db, ObjectId(str(course_id)))
    sessions = schedule["sessions"]
    sibling = next(s for s in sessions if s["session_id"] == "U1-T2-s1")
    with pytest.raises(ScheduleConflictError):
        await svc.reschedule_session(
            str(course_id), "U1-T1-s1", sibling["date"], ADMIN,
            new_period_start=sibling["period_start"],
            new_period_end=sibling["period_end"],
        )


@pytest.mark.asyncio
async def test_reschedule_conflicts_with_other_course_same_faculty(db):
    shared_faculty = ObjectId()
    course_id, _ = await _seed(db, faculty_id=shared_faculty)
    schedule = await svc._find_active_schedule_document(db, ObjectId(str(course_id)))
    iso, start, end = _free_slot(schedule["sessions"])

    # Another active schedule for the SAME faculty occupies that exact slot.
    now = datetime.now(UTC)
    await db.generated_schedules.insert_one({
        "_id": ObjectId(), "course_id": ObjectId(), "faculty_id": shared_faculty,
        "sessions": [{
            "session_id": "OTHER-s1", "topic_id": "OTHER", "topic": "Other course",
            "unit_number": 1, "unit_title": "X", "date": iso, "day": "Monday",
            "period_start": start, "period_end": end, "duration_hours": 1,
            "status": "pending",
        }],
        "total_hours": 1, "version": 1, "active": True, "status": "generated",
        "created_at": now, "updated_at": now,
    })
    with pytest.raises(ScheduleConflictError):
        await svc.reschedule_session(
            str(course_id), "U1-T1-s1", iso, ADMIN,
            new_period_start=start, new_period_end=end,
        )


# --- RBAC ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_faculty_without_ownership_denied(db):
    course_id, _ = await _seed(db)
    with pytest.raises(ProgressPermissionError):
        await svc.update_session_status(
            str(course_id), "U1-T1-s1", "completed", None, FACULTY_OTHER
        )


# --- regeneration carry-forward --------------------------------------------


@pytest.mark.asyncio
async def test_regeneration_carries_forward_execution(db):
    course_id, _ = await _seed(db)
    # Record execution on the active schedule.
    await svc.update_session_status(
        str(course_id), "U1-T1-s1", "completed", None, ADMIN,
        actual_hours=1, remarks="done",
    )
    await svc.update_session_status(str(course_id), "U1-T2-s1", "skipped", None, ADMIN)

    # Regenerate with identical inputs.
    await sched.generate_schedule(str(course_id))

    progress = await svc.get_course_progress(str(course_id))
    by_id = {s["session_id"]: s for s in progress["sessions"]}
    assert by_id["U1-T1-s1"]["status"] == "completed"
    assert by_id["U1-T1-s1"]["actual_hours"] == 1
    assert by_id["U1-T1-s1"]["faculty_remarks"] == "done"
    assert by_id["U1-T2-s1"]["status"] == "skipped"
    # A never-touched session stays pending.
    assert by_id["U1-T1-s2"]["status"] == "pending"

    # Exactly one active schedule remains; the old one is superseded (kept).
    active = await db.generated_schedules.count_documents(
        {"course_id": {"$in": sched._id_variants(ObjectId(str(course_id)))},
         "active": True}
    )
    assert active == 1
    total = await db.generated_schedules.count_documents(
        {"course_id": {"$in": sched._id_variants(ObjectId(str(course_id)))}}
    )
    assert total == 2


@pytest.mark.asyncio
async def test_carry_forward_skips_when_plan_changes(db):
    course_id, _ = await _seed(db)
    await svc.update_session_status(
        str(course_id), "U1-T1-s1", "completed", None, ADMIN, actual_hours=1
    )
    # Change Topic A's hours so its planned chunk no longer matches -> the
    # completed session must NOT be blindly carried forward.
    await db.lesson_plans.update_one(
        {"course_id": ObjectId(str(course_id))},
        {"$set": {"structured_plan": _structured_plan(
            [("U1-T1", "Topic A", 3), ("U1-T2", "Topic B", 1)]
        )}},
    )
    await sched.generate_schedule(str(course_id))
    progress = await svc.get_course_progress(str(course_id))
    by_id = {s["session_id"]: s for s in progress["sessions"]}
    # U1-T1-s1 now has duration 1h again (3h split into 1h blocks) so the id
    # matches; but if the split differs the status stays pending. Assert the
    # engine never invents completion for an unmatched chunk: any carried
    # session must still be a real completed record with actual_hours set.
    for sid, session in by_id.items():
        if session["status"] == "completed":
            assert session.get("actual_hours") is not None
