"""Integration tests for the calendar-aware, period-based scheduler service
(Task #5).

Uses an in-memory Mongo (``mongomock_motor``) so persistence, academic-year
calendar selection, period scheduling, blocked-range handling, special/swap
days, faculty validation and conflict detection are all verified offline.

Run: python -m pytest backend/tests/test_scheduler_service_periods.py -q
"""

import os
import sys
from datetime import datetime, UTC

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

import app.database.mongodb as mongodb
from app.services import scheduler_service as svc
from app.services.scheduler_engine import (
    ScheduleConflictError,
    SchedulerValidationError,
)


@pytest.fixture()
def db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    monkeypatch.setattr(mongodb, "database", database)
    return database


def _structured_plan(*specs):
    if not specs:
        specs = (("U1-T1", "Topic A", 2), ("U1-T2", "Topic B", 1))
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


PERIOD_SCHEDULE = [
    {"day": "Monday", "period_start": 1, "period_end": 1},
    {"day": "Monday", "period_start": 2, "period_end": 2},
    {"day": "Tuesday", "period_start": 5, "period_end": 5},
]


async def _seed_period(
    db,
    *,
    faculty_id=None,
    academic_year="2026-2027",
    calendar_academic_year="2026-2027",
    course_academic_year="2026-2027",
    holidays=None,
    blocked_periods=None,
    special_days=None,
    timetable_faculty_id="__same__",
    plan_specs=(),
):
    course_id = ObjectId()
    faculty_id = faculty_id or ObjectId()
    now = datetime.now(UTC)

    course = {
        "_id": course_id,
        "course_code": "CS101",
        "semester": 5,
        "faculty_id": faculty_id,
        "created_at": now,
    }
    if course_academic_year is not None:
        course["academic_year"] = course_academic_year
    await db.courses.insert_one(course)

    await db.lesson_plans.insert_one({
        "_id": ObjectId(),
        "course_id": course_id,
        "lesson_plan": "Topic A\nTopic B",
        "structured_plan": _structured_plan(*plan_specs),
        "created_at": now,
    })

    calendar = {
        "_id": ObjectId(),
        "semester": 5,
        "semester_start": "2026-07-27",  # Monday
        "semester_end": "2026-08-07",
        "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "holidays": holidays or [],
        "created_at": now,
    }
    if calendar_academic_year is not None:
        calendar["academic_year"] = calendar_academic_year
    if blocked_periods is not None:
        calendar["blocked_periods"] = blocked_periods
    if special_days is not None:
        calendar["special_days"] = special_days
    await db.academic_calendar.insert_one(calendar)

    tt_faculty = faculty_id if timetable_faculty_id == "__same__" else timetable_faculty_id
    await db.timetables.insert_one({
        "_id": ObjectId(),
        "faculty_id": tt_faculty,
        "course_id": course_id,
        "semester": 5,
        "academic_year": academic_year,
        "schedule": PERIOD_SCHEDULE,
        "created_at": now,
    })

    return course_id, faculty_id


@pytest.mark.asyncio
async def test_period_schedule_persists_and_uses_periods(db):
    course_id, _ = await _seed_period(db)
    result = await svc.generate_schedule(str(course_id))

    assert result["status"] == "generated"
    assert result["scheduling_mode"] == "period"
    assert result["academic_year"] == "2026-2027"
    assert result["total_hours"] == 3.0
    laid = [
        (s["date"], s["topic"], s["period_start"], s["period_end"])
        for s in result["sessions"]
    ]
    # Mon periods 1 & 2 (Topic A, 2h), Tuesday period 5 (Topic B, 1h).
    assert laid == [
        ("2026-07-27", "Topic A", 1, 1),
        ("2026-07-27", "Topic A", 2, 2),
        ("2026-07-28", "Topic B", 5, 5),
    ]


@pytest.mark.asyncio
async def test_calendar_selected_by_academic_year(db):
    # Two calendars for the same semester in different academic years — the
    # scheduler must pick the one matching the resolved academic year.
    course_id, _ = await _seed_period(
        db, course_academic_year="2027-2028", calendar_academic_year="2027-2028"
    )
    # Insert a decoy calendar for a different academic year, same semester.
    await db.academic_calendar.insert_one({
        "_id": ObjectId(),
        "academic_year": "2099-2100",
        "semester": 5,
        "semester_start": "2026-07-27",
        "semester_end": "2026-08-07",
        "working_days": ["Monday"],
        "created_at": datetime.now(UTC),
    })
    result = await svc.generate_schedule(str(course_id))
    assert result["academic_year"] == "2027-2028"


@pytest.mark.asyncio
async def test_2026_27_schedule_never_uses_2025_26_calendar(db):
    # Task #8.2 req. 3 scenario: two calendars for Semester 5 in adjacent
    # academic years. Generating the 2026-27 course schedule must select the
    # 2026-27 calendar and NEVER the 2025-26 one — even though the 2025-26
    # calendar is inserted afterwards (newest by created_at).
    course_id, _ = await _seed_period(
        db,
        course_academic_year="2026-2027",
        calendar_academic_year="2026-2027",
        academic_year="2026-2027",
    )
    # Decoy: a 2025-26 Semester 5 calendar with a clearly different (earlier)
    # semester window, inserted last so it is the newest document.
    await db.academic_calendar.insert_one({
        "_id": ObjectId(),
        "academic_year": "2025-2026",
        "semester": 5,
        "semester_start": "2025-07-28",
        "semester_end": "2025-08-08",
        "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "created_at": datetime.now(UTC),
    })

    result = await svc.generate_schedule(str(course_id))

    # Correct academic year selected …
    assert result["academic_year"] == "2026-2027"
    # … and every scheduled date lands in the 2026-27 window, proving the
    # 2025-26 calendar was not used.
    assert result["sessions"]
    assert all(s["date"].startswith("2026-") for s in result["sessions"])


@pytest.mark.asyncio
async def test_explicit_academic_year_arg_wins(db):
    course_id, _ = await _seed_period(
        db, course_academic_year=None, calendar_academic_year="2030-2031",
        academic_year=None,
    )
    result = await svc.generate_schedule(str(course_id), academic_year="2030-2031")
    assert result["academic_year"] == "2030-2031"


@pytest.mark.asyncio
async def test_ambiguous_academic_year_raises(db):
    # No academic-year context anywhere + multiple calendars for the semester
    # across different academic years -> controlled validation error.
    course_id, _ = await _seed_period(
        db, course_academic_year=None, calendar_academic_year="2026-2027",
        academic_year=None,
    )
    await db.academic_calendar.insert_one({
        "_id": ObjectId(),
        "academic_year": "2028-2029",
        "semester": 5,
        "semester_start": "2026-07-27",
        "semester_end": "2026-08-07",
        "working_days": ["Monday"],
        "created_at": datetime.now(UTC),
    })
    with pytest.raises(SchedulerValidationError) as exc:
        await svc.generate_schedule(str(course_id))
    assert "academic year" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_academic_year_calendar_not_found(db):
    course_id, _ = await _seed_period(
        db, course_academic_year="1900-1901", calendar_academic_year="2026-2027",
        academic_year=None,
    )
    with pytest.raises(svc.ScheduleNotFoundError) as exc:
        await svc.generate_schedule(str(course_id))
    assert "1900-1901" in str(exc.value)


@pytest.mark.asyncio
async def test_blocked_period_range_removes_days(db):
    # Block the whole first Monday+Tuesday so allocation starts the next week.
    course_id, _ = await _seed_period(
        db,
        blocked_periods=[
            {"name": "CIA I", "start_date": "2026-07-27", "end_date": "2026-07-28"}
        ],
    )
    result = await svc.generate_schedule(str(course_id))
    dates = {s["date"] for s in result["sessions"]}
    assert "2026-07-27" not in dates
    assert "2026-07-28" not in dates
    # Next Monday is 2026-08-03.
    assert "2026-08-03" in dates


@pytest.mark.asyncio
async def test_holiday_dict_shape_blocks_day(db):
    course_id, _ = await _seed_period(
        db, holidays=[{"date": "2026-07-27", "name": "Founder's Day"}]
    )
    result = await svc.generate_schedule(str(course_id))
    assert all(s["date"] != "2026-07-27" for s in result["sessions"])


@pytest.mark.asyncio
async def test_special_swap_day_uses_other_timetable(db):
    # Make Tuesday 2026-07-28 follow the MONDAY timetable, so Monday's periods
    # 1 & 2 also apply that day. With a single 3h topic + 1h topic there are now
    # enough Monday-style slots earlier in the week.
    course_id, _ = await _seed_period(
        db,
        special_days=[{"date": "2026-07-28", "timetable_day": "Monday"}],
        plan_specs=(("U1-T1", "A", 4),),
    )
    result = await svc.generate_schedule(str(course_id))
    # Tuesday now carries Monday periods 1 & 2 (from the swap) PLUS its own
    # period 5 is gone (Tuesday timetable replaced by Monday timetable).
    tue = [s for s in result["sessions"] if s["date"] == "2026-07-28"]
    assert {s["period_start"] for s in tue} == {1, 2}


@pytest.mark.asyncio
async def test_faculty_mismatch_rejected(db):
    course_id, _ = await _seed_period(db, timetable_faculty_id=ObjectId())
    with pytest.raises(SchedulerValidationError) as exc:
        await svc.generate_schedule(str(course_id))
    assert "faculty" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_period_conflict_same_faculty(db):
    shared = ObjectId()
    course_a, _ = await _seed_period(db, faculty_id=shared)
    await svc.generate_schedule(str(course_a))

    course_b, _ = await _seed_period(db, faculty_id=shared)
    with pytest.raises(ScheduleConflictError) as exc:
        await svc.generate_schedule(str(course_b))
    assert exc.value.conflicts
    assert exc.value.conflicts[0]["reason"].startswith("Faculty already teaching")


@pytest.mark.asyncio
async def test_conflict_not_persisted(db):
    shared = ObjectId()
    course_a, _ = await _seed_period(db, faculty_id=shared)
    await svc.generate_schedule(str(course_a))
    course_b, _ = await _seed_period(db, faculty_id=shared)
    with pytest.raises(ScheduleConflictError):
        await svc.generate_schedule(str(course_b))
    # Only course_a's schedule was ever stored.
    stored = await db.generated_schedules.count_documents({})
    assert stored == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
