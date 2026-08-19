"""Integration tests for the scheduler service (Phase 16).

Uses an in-memory Mongo (``mongomock_motor``) instead of a real Atlas cluster
or Groq, so persistence, regeneration, conflict detection and the not-found
paths are all verified deterministically and offline.

Run: python -m pytest backend/tests/test_scheduler_service.py -q
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
from app.services.scheduler_engine import ScheduleConflictError, SchedulerValidationError


@pytest.fixture()
def db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    # get_database() returns the module global; point it at the mock.
    monkeypatch.setattr(mongodb, "database", database)
    return database


def _structured_plan():
    return {
        "units": [
            {
                "unit_number": 1,
                "unit_title": "Introduction",
                "topics": [
                    {"topic_id": "U1-T1", "topic": "Topic A", "estimated_hours": 2},
                    {"topic_id": "U1-T2", "topic": "Topic B", "estimated_hours": 1},
                ],
            }
        ]
    }


async def _seed(db, *, with_plan=True, structured=True, with_calendar=True,
                with_timetable=True, faculty_id=None):
    course_id = ObjectId()
    faculty_id = faculty_id or ObjectId()
    now = datetime.now(UTC)

    await db.courses.insert_one({
        "_id": course_id,
        "course_code": "CS101",
        "semester": 5,
        "faculty_id": faculty_id,
        "created_at": now,
    })

    syllabus_id = ObjectId()
    await db.syllabi.insert_one({
        "_id": syllabus_id, "course_id": course_id, "text": "syllabus", "created_at": now,
    })

    if with_plan:
        await db.lesson_plans.insert_one({
            "_id": ObjectId(),
            "course_id": course_id,
            "syllabus_id": syllabus_id,
            "lesson_plan": "Topic A\nTopic B",
            "structured_plan": _structured_plan() if structured else None,
            "created_at": now,
        })

    if with_calendar:
        await db.academic_calendar.insert_one({
            "_id": ObjectId(),
            "semester": 5,
            "semester_start": "2026-07-27",  # Monday
            "semester_end": "2026-08-07",
            "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "holidays": [],
            "internal_exams": [],
            "created_at": now,
        })

    if with_timetable:
        await db.timetables.insert_one({
            "_id": ObjectId(),
            "faculty_id": faculty_id,
            "course_id": course_id,
            "semester": 5,
            "schedule": [
                {"day": "Monday", "start_time": "09:00", "end_time": "10:00"},
                {"day": "Wednesday", "start_time": "11:00", "end_time": "12:00"},
                {"day": "Friday", "start_time": "14:00", "end_time": "15:00"},
            ],
            "created_at": now,
        })

    return course_id, faculty_id


@pytest.mark.asyncio
async def test_generate_persists_and_returns_sessions(db):
    course_id, faculty_id = await _seed(db)
    result = await svc.generate_schedule(str(course_id))

    assert result["status"] == "generated"
    assert result["version"] == 1
    assert result["total_hours"] == 3.0
    assert result["workload"]["total_hours"] == 3.0
    assert [(s["date"], s["topic"]) for s in result["sessions"]] == [
        ("2026-07-27", "Topic A"),
        ("2026-07-29", "Topic A"),
        ("2026-07-31", "Topic B"),
    ]

    stored = await db.generated_schedules.count_documents({})
    assert stored == 1


@pytest.mark.asyncio
async def test_get_latest_schedule(db):
    course_id, _ = await _seed(db)
    await svc.generate_schedule(str(course_id))
    fetched = await svc.get_latest_schedule(str(course_id))
    assert fetched["version"] == 1
    assert fetched["active"] is True


@pytest.mark.asyncio
async def test_get_latest_missing_raises(db):
    course_id, _ = await _seed(db)
    with pytest.raises(svc.ScheduleNotFoundError):
        await svc.get_latest_schedule(str(course_id))


@pytest.mark.asyncio
async def test_regeneration_supersedes_previous(db):
    course_id, _ = await _seed(db)
    await svc.generate_schedule(str(course_id))
    second = await svc.generate_schedule(str(course_id))

    assert second["version"] == 2
    assert second["active"] is True
    # Old version marked inactive, not deleted.
    total = await db.generated_schedules.count_documents({})
    assert total == 2
    active = await db.generated_schedules.count_documents({
        "course_id": course_id, "active": True
    })
    assert active == 1
    latest = await svc.get_latest_schedule(str(course_id))
    assert latest["version"] == 2


@pytest.mark.asyncio
async def test_conflict_with_other_course_same_faculty(db):
    shared_faculty = ObjectId()
    course_a, _ = await _seed(db, faculty_id=shared_faculty)
    await svc.generate_schedule(str(course_a))

    # Second course, SAME faculty, same timetable slots -> conflict.
    course_b, _ = await _seed(db, faculty_id=shared_faculty)
    with pytest.raises(ScheduleConflictError) as exc:
        await svc.generate_schedule(str(course_b))
    assert exc.value.conflicts
    assert exc.value.conflicts[0]["reason"].startswith("Faculty already teaching")


@pytest.mark.asyncio
async def test_missing_structured_plan_backward_compat(db):
    # Old lesson plan with structured_plan = None -> controlled validation error.
    course_id, _ = await _seed(db, structured=False)
    with pytest.raises(SchedulerValidationError) as exc:
        await svc.generate_schedule(str(course_id))
    assert "Regenerate the lesson plan" in str(exc.value)


@pytest.mark.asyncio
async def test_missing_course(db):
    with pytest.raises(svc.ScheduleNotFoundError) as exc:
        await svc.generate_schedule(str(ObjectId()))
    assert "Course not found" in str(exc.value)


@pytest.mark.asyncio
async def test_missing_lesson_plan(db):
    course_id, _ = await _seed(db, with_plan=False)
    with pytest.raises(svc.ScheduleNotFoundError) as exc:
        await svc.generate_schedule(str(course_id))
    assert "Lesson plan not found" in str(exc.value)


@pytest.mark.asyncio
async def test_missing_calendar(db):
    course_id, _ = await _seed(db, with_calendar=False)
    with pytest.raises(svc.ScheduleNotFoundError) as exc:
        await svc.generate_schedule(str(course_id))
    assert "calendar" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_missing_timetable(db):
    course_id, _ = await _seed(db, with_timetable=False)
    with pytest.raises(svc.ScheduleNotFoundError) as exc:
        await svc.generate_schedule(str(course_id))
    assert "Timetable not found" in str(exc.value)


@pytest.mark.asyncio
async def test_malformed_course_id(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.generate_schedule("not-an-objectid")
    assert exc.value.status_code == 400
