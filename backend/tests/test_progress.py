"""Tests for progress monitoring + schedule-deviation tracking (Phase 18).

Two layers:
  - ``progress_engine`` is pure, so it is tested with fixed dates and plain
    session dicts (no MongoDB, no system-date reliance).
  - ``progress_service`` is tested against an in-memory Mongo
    (``mongomock_motor``) covering status updates, ownership/RBAC and the
    not-found paths.

Run: python -m pytest backend/tests/test_progress.py -q
"""

import os
import sys
from datetime import date, datetime, UTC

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

import app.database.mongodb as mongodb
from app.services import progress_engine as eng
from app.services import progress_service as svc

# Fixed reference date so nothing depends on the real system clock.
TODAY = date(2026, 8, 10)


def _session(topic_id, topic, unit_number, unit_title, planned, hours, status="pending",
             actual_date=None):
    s = {
        "topic_id": topic_id,
        "topic": topic,
        "unit_number": unit_number,
        "unit_title": unit_title,
        "date": planned,
        "day": "Monday",
        "start_time": "09:00",
        "end_time": "10:00",
        "duration_hours": hours,
        "status": status,
    }
    if actual_date is not None:
        s["actual_date"] = actual_date
    return s


# ---------------------------------------------------------------------------
# Pure engine tests
# ---------------------------------------------------------------------------


def test_empty_progress():
    result = eng.compute_progress([], TODAY)
    summary = result["summary"]
    assert summary["total_sessions"] == 0
    assert summary["total_planned_hours"] == 0
    assert summary["completion_percentage"] == 0.0
    assert summary["planned_progress_percentage"] == 0.0
    assert summary["deviation_percentage"] == 0.0
    assert result["units"] == []
    assert result["topics"] == []
    assert result["deviations"] == []


def test_all_pending():
    sessions = [
        _session("U1-T1", "A", 1, "Intro", "2026-08-20", 2),
        _session("U1-T2", "B", 1, "Intro", "2026-08-21", 2),
    ]
    summary = eng.build_summary(sessions, TODAY)
    assert summary["total_sessions"] == 2
    assert summary["pending_sessions"] == 2
    assert summary["completed_sessions"] == 0
    assert summary["completed_hours"] == 0
    # Both planned in the future -> nothing due yet.
    assert summary["planned_progress_percentage"] == 0.0
    assert summary["deviation_percentage"] == 0.0


def test_one_completed_session():
    sessions = [
        _session("U1-T1", "A", 1, "Intro", "2026-08-05", 2, status="completed"),
        _session("U1-T2", "B", 1, "Intro", "2026-08-20", 2),
    ]
    summary = eng.build_summary(sessions, TODAY)
    assert summary["completed_sessions"] == 1
    assert summary["completed_hours"] == 2
    assert summary["completion_percentage"] == 50.0


def test_multiple_completed_sessions():
    sessions = [
        _session("U1-T1", "A", 1, "Intro", "2026-08-01", 2, status="completed"),
        _session("U1-T2", "B", 1, "Intro", "2026-08-02", 2, status="completed"),
        _session("U2-T1", "C", 2, "Core", "2026-08-20", 4),
    ]
    summary = eng.build_summary(sessions, TODAY)
    assert summary["completed_hours"] == 4
    assert summary["completion_percentage"] == 50.0


def test_skipped_session_counted_and_flagged():
    sessions = [_session("U1-T1", "A", 1, "Intro", "2026-08-05", 2, status="skipped")]
    result = eng.compute_progress(sessions, TODAY)
    assert result["summary"]["skipped_sessions"] == 1
    types = [d["type"] for d in result["deviations"]]
    assert "skipped" in types
    dev = next(d for d in result["deviations"] if d["type"] == "skipped")
    assert dev["severity"] == "medium"


def test_rescheduled_session_and_actual_date():
    sessions = [
        _session("U1-T1", "A", 1, "Intro", "2026-08-05", 2, status="rescheduled",
                 actual_date="2026-08-07"),
    ]
    result = eng.compute_progress(sessions, TODAY)
    assert result["summary"]["rescheduled_sessions"] == 1
    dev = next(d for d in result["deviations"] if d["type"] == "rescheduled")
    assert dev["severity"] == "medium"
    assert dev["planned_date"] == "2026-08-05"
    assert dev["actual_date"] == "2026-08-07"


def test_overdue_pending_session():
    sessions = [_session("U1-T1", "A", 1, "Intro", "2026-08-01", 2)]  # < today, pending
    result = eng.compute_progress(sessions, TODAY)
    dev = next(d for d in result["deviations"] if d["type"] == "overdue")
    assert dev["severity"] == "high"
    assert dev["session_id"] == 0


def test_future_pending_not_overdue():
    sessions = [_session("U1-T1", "A", 1, "Intro", "2026-08-20", 2)]  # future, pending
    result = eng.compute_progress(sessions, TODAY)
    assert all(d["type"] != "overdue" for d in result["deviations"])


def test_today_pending_not_overdue():
    sessions = [_session("U1-T1", "A", 1, "Intro", TODAY.isoformat(), 2)]
    result = eng.compute_progress(sessions, TODAY)
    assert all(d["type"] != "overdue" for d in result["deviations"])


def test_planned_and_actual_progress_and_negative_deviation():
    # 100 total hours; 60h planned by today; 45h actually completed.
    sessions = [
        _session("U1-T1", "A", 1, "Intro", "2026-08-01", 45, status="completed"),
        _session("U1-T2", "B", 1, "Intro", "2026-08-05", 15),   # due, still pending
        _session("U2-T1", "C", 2, "Core", "2026-08-20", 40),    # future
    ]
    summary = eng.build_summary(sessions, TODAY)
    assert summary["total_planned_hours"] == 100
    assert summary["planned_progress_percentage"] == 60.0
    assert summary["actual_progress_percentage"] == 45.0
    assert summary["deviation_percentage"] == -15.0


def test_positive_deviation_ahead_of_schedule():
    # Completed more than what was due by today -> positive deviation.
    sessions = [
        _session("U1-T1", "A", 1, "Intro", "2026-08-01", 30, status="completed"),
        _session("U1-T2", "B", 1, "Intro", "2026-08-20", 20, status="completed"),
        _session("U2-T1", "C", 2, "Core", "2026-08-21", 50),
    ]
    summary = eng.build_summary(sessions, TODAY)
    assert summary["planned_progress_percentage"] == 30.0
    assert summary["actual_progress_percentage"] == 50.0
    assert summary["deviation_percentage"] == 20.0
    # No behind_schedule deviation when ahead.
    result = eng.compute_progress(sessions, TODAY)
    assert all(d["type"] != "behind_schedule" for d in result["deviations"])


def test_behind_schedule_severity_bands():
    assert eng._behind_schedule_severity(-3) == "low"
    assert eng._behind_schedule_severity(-5) == "medium"
    assert eng._behind_schedule_severity(-10) == "medium"
    assert eng._behind_schedule_severity(-15) == "high"
    assert eng._behind_schedule_severity(-30) == "high"


def test_topic_progress_grouping():
    sessions = [
        _session("U1-T1", "A", 1, "Intro", "2026-08-01", 1, status="completed"),
        _session("U1-T1", "A", 1, "Intro", "2026-08-02", 1),  # same topic, pending
    ]
    topics = eng.build_topic_progress(sessions)
    assert len(topics) == 1
    assert topics[0]["topic_id"] == "U1-T1"
    assert topics[0]["planned_hours"] == 2
    assert topics[0]["completed_hours"] == 1
    assert topics[0]["completion_percentage"] == 50.0


def test_topic_grouping_by_id_not_name():
    # Two topics share a name but differ by id -> must stay separate.
    sessions = [
        _session("U1-T1", "Dup", 1, "Intro", "2026-08-01", 1),
        _session("U2-T1", "Dup", 2, "Core", "2026-08-02", 1),
    ]
    topics = eng.build_topic_progress(sessions)
    assert {t["topic_id"] for t in topics} == {"U1-T1", "U2-T1"}


def test_unit_progress_grouping():
    sessions = [
        _session("U1-T1", "A", 1, "Intro", "2026-08-01", 5, status="completed"),
        _session("U1-T2", "B", 1, "Intro", "2026-08-02", 5),
        _session("U2-T1", "C", 2, "Core", "2026-08-03", 4, status="completed"),
    ]
    units = eng.build_unit_progress(sessions)
    unit1 = next(u for u in units if u["unit_number"] == 1)
    assert unit1["planned_hours"] == 10
    assert unit1["completed_hours"] == 5
    assert unit1["completion_percentage"] == 50.0


def test_zero_hour_schedule_no_division_error():
    sessions = [_session("U1-T1", "A", 1, "Intro", "2026-08-01", 0, status="completed")]
    summary = eng.build_summary(sessions, TODAY)
    assert summary["total_planned_hours"] == 0
    assert summary["completion_percentage"] == 0.0
    assert summary["deviation_percentage"] == 0.0


# ---------------------------------------------------------------------------
# Service tests (mongomock)
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    monkeypatch.setattr(mongodb, "database", database)
    # Freeze "today" for deterministic deviation math.
    monkeypatch.setattr(svc, "_today", lambda: TODAY)
    return database


ADMIN = {"id": "u1", "email": "admin@x.edu", "role": "admin"}
HOD = {"id": "u2", "email": "hod@x.edu", "role": "hod"}


async def _seed_schedule(db, faculty_id=None, sessions=None):
    course_id = ObjectId()
    faculty_id = faculty_id if faculty_id is not None else ObjectId()
    now = datetime.now(UTC)
    await db.courses.insert_one({"_id": course_id, "faculty_id": faculty_id, "semester": 5})
    if sessions is None:
        sessions = [
            _session("U1-T1", "A", 1, "Intro", "2026-08-01", 2),
            _session("U1-T2", "B", 1, "Intro", "2026-08-20", 2),
        ]
    await db.generated_schedules.insert_one({
        "_id": ObjectId(),
        "course_id": course_id,
        "faculty_id": faculty_id,
        "sessions": sessions,
        "total_hours": 4,
        "version": 1,
        "active": True,
        "status": "generated",
        "created_at": now,
        "updated_at": now,
    })
    return course_id


@pytest.mark.asyncio
async def test_service_get_progress(db):
    course_id = await _seed_schedule(db)
    result = await svc.get_course_progress(str(course_id))
    assert result["summary"]["total_sessions"] == 2
    # first session is overdue+pending (2026-08-01 < TODAY)
    assert any(d["type"] == "overdue" for d in result["deviations"])
    assert all("session_id" in s for s in result["sessions"])


@pytest.mark.asyncio
async def test_service_update_completed(db):
    course_id = await _seed_schedule(db)
    result = await svc.update_session_status(
        str(course_id), "0", "completed", None, ADMIN
    )
    assert result["session"]["status"] == "completed"
    assert result["session"]["session_id"] == 0
    # Persisted + only that session changed.
    progress = await svc.get_course_progress(str(course_id))
    assert progress["summary"]["completed_sessions"] == 1
    assert progress["sessions"][1]["status"] == "pending"


@pytest.mark.asyncio
async def test_service_reschedule_preserves_planned_date(db):
    course_id = await _seed_schedule(db)
    result = await svc.update_session_status(
        str(course_id), "0", "rescheduled", "2026-08-07", ADMIN
    )
    assert result["session"]["status"] == "rescheduled"
    assert result["session"]["date"] == "2026-08-01"       # original preserved
    assert result["session"]["actual_date"] == "2026-08-07"  # new date stored


@pytest.mark.asyncio
async def test_service_hod_can_update(db):
    course_id = await _seed_schedule(db)
    result = await svc.update_session_status(str(course_id), "1", "skipped", None, HOD)
    assert result["session"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_service_faculty_owner_by_email(db):
    faculty_id = ObjectId()
    await db.faculty.insert_one({
        "_id": faculty_id, "faculty_id": "F01", "email": "prof@x.edu", "name": "Prof",
    })
    course_id = await _seed_schedule(db, faculty_id=faculty_id)
    owner = {"id": "u9", "email": "prof@x.edu", "role": "faculty"}
    result = await svc.update_session_status(str(course_id), "0", "completed", None, owner)
    assert result["session"]["status"] == "completed"


@pytest.mark.asyncio
async def test_service_faculty_non_owner_denied(db):
    faculty_id = ObjectId()
    await db.faculty.insert_one({
        "_id": faculty_id, "faculty_id": "F01", "email": "prof@x.edu", "name": "Prof",
    })
    course_id = await _seed_schedule(db, faculty_id=faculty_id)
    other = {"id": "u9", "email": "other@x.edu", "role": "faculty"}
    with pytest.raises(svc.ProgressPermissionError):
        await svc.update_session_status(str(course_id), "0", "completed", None, other)


@pytest.mark.asyncio
async def test_service_faculty_unresolvable_denied(db):
    # No faculty document to resolve -> ownership cannot be established -> denied.
    course_id = await _seed_schedule(db, faculty_id="unknown-code")
    fac = {"id": "u9", "email": "prof@x.edu", "role": "faculty"}
    with pytest.raises(svc.ProgressPermissionError):
        await svc.update_session_status(str(course_id), "0", "completed", None, fac)


@pytest.mark.asyncio
async def test_service_missing_course(db):
    with pytest.raises(svc.ScheduleNotFoundError) as exc:
        await svc.get_course_progress(str(ObjectId()))
    assert "Course not found" in str(exc.value)


@pytest.mark.asyncio
async def test_service_missing_schedule(db):
    course_id = ObjectId()
    await db.courses.insert_one({"_id": course_id, "faculty_id": ObjectId()})
    with pytest.raises(svc.ScheduleNotFoundError) as exc:
        await svc.get_course_progress(str(course_id))
    assert "schedule" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_service_missing_session(db):
    course_id = await _seed_schedule(db)
    with pytest.raises(svc.SessionNotFoundError):
        await svc.update_session_status(str(course_id), "99", "completed", None, ADMIN)


@pytest.mark.asyncio
async def test_service_non_integer_session_id(db):
    course_id = await _seed_schedule(db)
    with pytest.raises(svc.SessionNotFoundError):
        await svc.update_session_status(str(course_id), "abc", "completed", None, ADMIN)


@pytest.mark.asyncio
async def test_service_malformed_course_id(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.get_course_progress("not-an-objectid")
    assert exc.value.status_code == 400
