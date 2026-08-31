"""HTTP-level authorization tests for the /scheduler router (IDOR fix).

The previously discovered vulnerability was an Insecure Direct Object Reference
(IDOR): every ``/scheduler/{course_id}`` route required only a valid JWT, so any
authenticated faculty could read, generate, regenerate, export or mutate ANOTHER
faculty's course schedule purely by changing the ``course_id`` in the URL.

These tests exercise the real ASGI app through ``TestClient`` (not the service
functions directly), because the vulnerability lived at the HTTP boundary and
must be proven fixed at that same boundary. They mirror the ownership model used
elsewhere in the suite:

    * Faculty A owns Course A (``courses.faculty_id`` -> ``faculty._id``),
      linked to the authenticated user by shared email.
    * Faculty B is a legitimate, unrelated faculty user.
    * Admin is a manager who may access any course.

Every scheduler route is checked for three outcomes:

    Faculty B (not the owner) -> 403 on read / generate / regenerate / progress /
                                 export / session mutation.
    Faculty A (the owner)     -> allowed.
    Admin (manager)           -> allowed.

Plus id-handling edge cases (malformed id -> 400, unknown course -> 404) and the
guarantee that an unauthorized destructive regenerate never mutates the data.
"""

import asyncio
from datetime import UTC, datetime

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import app.database.mongodb as mongodb
from app.api.v1.scheduler import router as scheduler_router
from app.auth.jwt import create_access_token
from app.services.ai_service import merge_enrichment
from app.services.syllabus_parser import parse_syllabus


SYLLABUS = """
Course Code: CS8491
Course Title: Computer Architecture

UNIT I BASIC STRUCTURE OF A COMPUTER SYSTEM 9
Functional Units. Basic Operational Concepts. Performance.
UNIT II ARITHMETIC 9
Addition of Signed Numbers. Multiplication. Division.
"""


def _run(coro):
    return asyncio.run(coro)


def _headers(user_id: str, role: str) -> dict:
    token = create_access_token({"sub": str(user_id), "role": role})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    monkeypatch.setattr(mongodb, "database", database)
    return database


@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(scheduler_router)
    return TestClient(app)


@pytest.fixture()
def world(db, client):
    """Seed Faculty A (course owner), Faculty B, an admin and a live schedule.

    Faculty A's course is fully set up (lesson plan + calendar + timetable) and
    Faculty A generates a real schedule through the HTTP API, so every read /
    export / mutate route has genuine data to act on. Returns the identity
    headers, the course id and one addressable session id.
    """
    now = datetime.now(UTC)

    fac_a_user, fac_a = ObjectId(), ObjectId()
    course_a = ObjectId()
    _run(db.users.insert_one(
        {"_id": fac_a_user, "email": "a@x.edu", "role": "faculty", "created_at": now}
    ))
    _run(db.faculty.insert_one(
        {"_id": fac_a, "user_id": fac_a_user, "faculty_id": "F-A",
         "email": "a@x.edu", "created_at": now}
    ))
    _run(db.courses.insert_one(
        {"_id": course_a, "course_code": "CS8491", "semester": 5,
         "faculty_id": fac_a, "academic_year": "2026-2027", "created_at": now}
    ))

    canonical = parse_syllabus(SYLLABUS)
    plan = merge_enrichment(canonical, None, course_title=canonical.course_title)
    _run(db.lesson_plans.insert_one(
        {"_id": ObjectId(), "course_id": course_a,
         "structured_plan": plan.model_dump(mode="json"), "created_at": now}
    ))
    _run(db.academic_calendar.insert_one(
        {"_id": ObjectId(), "academic_year": "2026-2027", "semester": 5,
         "semester_start": "2026-08-03", "semester_end": "2026-12-18",
         "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
         "holidays": [], "created_at": now}
    ))
    _run(db.timetables.insert_one(
        {"_id": ObjectId(), "faculty_id": fac_a, "course_id": course_a,
         "semester": 5, "academic_year": "2026-2027",
         "schedule": [{"day": "Monday", "period_start": 1, "period_end": 2},
                      {"day": "Wednesday", "period_start": 3, "period_end": 4},
                      {"day": "Friday", "period_start": 5, "period_end": 6}],
         "created_at": now}
    ))

    # Faculty B — a legitimate but unrelated faculty user.
    fac_b_user, fac_b = ObjectId(), ObjectId()
    _run(db.users.insert_one(
        {"_id": fac_b_user, "email": "b@x.edu", "role": "faculty", "created_at": now}
    ))
    _run(db.faculty.insert_one(
        {"_id": fac_b, "user_id": fac_b_user, "faculty_id": "F-B",
         "email": "b@x.edu", "created_at": now}
    ))

    # An admin manager.
    admin_user = ObjectId()
    _run(db.users.insert_one(
        {"_id": admin_user, "email": "admin@x.edu", "role": "admin", "created_at": now}
    ))

    headers_a = _headers(fac_a_user, "faculty")
    headers_b = _headers(fac_b_user, "faculty")
    headers_admin = _headers(admin_user, "admin")
    cid = str(course_a)

    # Faculty A generates their own schedule (legitimate) so reads/exports work.
    r = client.post(f"/scheduler/{cid}", headers=headers_a)
    assert r.status_code == 200, r.text
    sessions = r.json().get("sessions") or []
    session_id = sessions[0].get("session_id", 0) if sessions else 0

    return {
        "cid": cid,
        "session_id": session_id,
        "headers_a": headers_a,
        "headers_b": headers_b,
        "headers_admin": headers_admin,
    }


# ---------------------------------------------------------------------------
# Faculty B (NOT the owner) must be blocked with 403 on every route
# ---------------------------------------------------------------------------


def test_faculty_b_cannot_read_schedule(world, client):
    r = client.get(f"/scheduler/{world['cid']}", headers=world["headers_b"])
    assert r.status_code == 403


def test_faculty_b_cannot_generate_schedule(world, client):
    r = client.post(f"/scheduler/{world['cid']}", headers=world["headers_b"])
    assert r.status_code == 403


def test_faculty_b_cannot_regenerate_schedule_and_data_is_untouched(world, client, db):
    """A destructive regenerate by a non-owner must be refused AND be a no-op."""
    cid = world["cid"]
    before = _run(db.generated_schedules.count_documents({}))
    active_before = _run(
        db.generated_schedules.find_one({"course_id": ObjectId(cid), "active": True})
    )

    r = client.post(f"/scheduler/{cid}", headers=world["headers_b"])
    assert r.status_code == 403

    after = _run(db.generated_schedules.count_documents({}))
    active_after = _run(
        db.generated_schedules.find_one({"course_id": ObjectId(cid), "active": True})
    )
    # No new version created, and the original active schedule is unchanged.
    assert after == before
    assert active_after["_id"] == active_before["_id"]
    assert active_after["version"] == active_before["version"]


def test_faculty_b_cannot_read_progress(world, client):
    r = client.get(f"/scheduler/{world['cid']}/progress", headers=world["headers_b"])
    assert r.status_code == 403


@pytest.mark.parametrize("fmt", ["pdf", "docx", "xlsx"])
def test_faculty_b_cannot_export(world, client, fmt):
    r = client.get(
        f"/scheduler/{world['cid']}/export/{fmt}", headers=world["headers_b"]
    )
    assert r.status_code == 403


def test_faculty_b_cannot_patch_session(world, client):
    r = client.patch(
        f"/scheduler/{world['cid']}/sessions/{world['session_id']}",
        headers=world["headers_b"],
        json={"status": "completed"},
    )
    assert r.status_code == 403


def test_faculty_b_cannot_reschedule_session(world, client):
    r = client.post(
        f"/scheduler/{world['cid']}/sessions/{world['session_id']}/reschedule",
        headers=world["headers_b"],
        json={"new_date": "2026-08-10"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Faculty A (the owner) is allowed on every route
# ---------------------------------------------------------------------------


def test_faculty_a_can_read_own_schedule(world, client):
    r = client.get(f"/scheduler/{world['cid']}", headers=world["headers_a"])
    assert r.status_code == 200


def test_faculty_a_can_read_own_progress(world, client):
    r = client.get(f"/scheduler/{world['cid']}/progress", headers=world["headers_a"])
    assert r.status_code == 200


def test_faculty_a_can_regenerate_own_schedule(world, client):
    r = client.post(f"/scheduler/{world['cid']}", headers=world["headers_a"])
    assert r.status_code == 200


@pytest.mark.parametrize("fmt", ["pdf", "docx", "xlsx"])
def test_faculty_a_can_export_own_schedule(world, client, fmt):
    r = client.get(
        f"/scheduler/{world['cid']}/export/{fmt}", headers=world["headers_a"]
    )
    assert r.status_code == 200


def test_faculty_a_can_patch_own_session(world, client):
    r = client.patch(
        f"/scheduler/{world['cid']}/sessions/{world['session_id']}",
        headers=world["headers_a"],
        json={"status": "completed"},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Admin (manager) may access any course
# ---------------------------------------------------------------------------


def test_admin_can_read_any_schedule(world, client):
    r = client.get(f"/scheduler/{world['cid']}", headers=world["headers_admin"])
    assert r.status_code == 200


def test_admin_can_regenerate_any_schedule(world, client):
    r = client.post(f"/scheduler/{world['cid']}", headers=world["headers_admin"])
    assert r.status_code == 200


def test_admin_can_export_any_schedule(world, client):
    r = client.get(
        f"/scheduler/{world['cid']}/export/pdf", headers=world["headers_admin"]
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Unauthenticated + id-handling edge cases
# ---------------------------------------------------------------------------


def test_unauthenticated_is_rejected(world, client):
    assert client.get(f"/scheduler/{world['cid']}").status_code in (401, 403)


def test_malformed_course_id_is_400(world, client):
    r = client.get("/scheduler/not-a-valid-id", headers=world["headers_a"])
    assert r.status_code == 400


def test_unknown_course_is_404_for_manager(world, client):
    r = client.get(f"/scheduler/{ObjectId()}", headers=world["headers_admin"])
    assert r.status_code == 404


def test_unknown_course_is_403_or_404_for_faculty(world, client):
    # A faculty user asking for a course that does not exist must never be told
    # it exists; 403 (cannot access) or 404 (not found) are both acceptable —
    # never a 200.
    r = client.get(f"/scheduler/{ObjectId()}", headers=world["headers_b"])
    assert r.status_code in (403, 404)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
