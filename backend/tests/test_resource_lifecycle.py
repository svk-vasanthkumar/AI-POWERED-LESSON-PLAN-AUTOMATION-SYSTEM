"""Task #8.2 — resource lifecycle / orphan-protection tests.

Extends the deletion dependency-protection guarantees already covered for
course + syllabus (see ``tests/test_task8_management.py``) to the remaining
resources whose deletion could otherwise leave dangling references:

    faculty     -> courses / timetables / generated schedules
    timetable   -> generated schedules
    lesson plan -> generated schedules

Guiding principle (Task #8.2): a delete must NEVER report success if it would
leave misleading dependent references. Dependency protection returns HTTP 409
instead of performing a destructive cascade.

Style mirrors ``tests/test_task8_management.py``: synchronous tests drive the
ASGI app through ``TestClient`` against an in-memory ``mongomock_motor``
database with real Bearer JWTs; seeding runs on a short-lived loop via ``_run``.
"""

import asyncio

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import app.database.mongodb as mongodb
from app.api.v1.faculty import router as faculty_router
from app.api.v1.lesson_plan import router as lesson_router
from app.api.v1.timetable import router as timetable_router
from app.auth.jwt import create_access_token


def _run(coro):
    return asyncio.run(coro)


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
    app.include_router(faculty_router)
    app.include_router(timetable_router)
    app.include_router(lesson_router)
    return TestClient(app)


@pytest.fixture()
def admin(db):
    uid = ObjectId()
    email = "admin@example.com"
    _run(
        db.users.insert_one(
            {"_id": uid, "name": "Admin", "email": email, "role": "admin"}
        )
    )
    token = create_access_token({"sub": str(uid), "role": "admin", "email": email})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


async def _make_faculty(db):
    res = await db.faculty.insert_one(
        {
            "faculty_id": "FAC-1",
            "name": "Prof",
            "email": "prof@example.com",
            "department": "CSE",
            "designation": "Professor",
        }
    )
    return res.inserted_id


async def _make_timetable(db, faculty_oid=None, course_oid=None):
    res = await db.timetables.insert_one(
        {
            "faculty_id": faculty_oid or ObjectId(),
            "course_id": course_oid or ObjectId(),
            "semester": 1,
            "schedule": [],
        }
    )
    return res.inserted_id


async def _make_lesson_plan(db, course_oid=None):
    res = await db.lesson_plans.insert_one(
        {
            "course_id": course_oid or ObjectId(),
            "syllabus_id": ObjectId(),
            "lesson_plan": "Topic Alpha",
            "structured_plan": {},
        }
    )
    return res.inserted_id


# ===========================================================================
# Faculty deletion — courses / timetables / generated schedules
# ===========================================================================


@pytest.mark.parametrize(
    "collection,doc_factory",
    [
        ("courses", lambda fid: {"course_code": "CS101", "faculty_id": fid}),
        ("timetables", lambda fid: {"faculty_id": fid, "course_id": ObjectId(), "schedule": []}),
        ("generated_schedules", lambda fid: {"faculty_id": fid, "sessions": []}),
    ],
)
def test_delete_faculty_blocked_by_each_dependent(client, admin, db, collection, doc_factory):
    faculty_oid = _run(_make_faculty(db))
    _run(db[collection].insert_one(doc_factory(faculty_oid)))

    r = client.request("DELETE", f"/faculty/{faculty_oid}", headers=admin)
    assert r.status_code == 409
    # The faculty must still exist — the delete was refused, not partial.
    assert _run(db.faculty.find_one({"_id": faculty_oid})) is not None


def test_delete_faculty_without_dependents_succeeds(client, admin, db):
    faculty_oid = _run(_make_faculty(db))
    r = client.request("DELETE", f"/faculty/{faculty_oid}", headers=admin)
    assert r.status_code == 200
    assert _run(db.faculty.find_one({"_id": faculty_oid})) is None


def test_delete_unknown_faculty_is_404(client, admin):
    assert (
        client.request("DELETE", f"/faculty/{ObjectId()}", headers=admin).status_code
        == 404
    )


def test_delete_faculty_with_string_reference_still_blocked(client, admin, db):
    # Legacy documents may store faculty_id as a plain string; protection must
    # still catch them so a delete never silently orphans them.
    faculty_oid = _run(_make_faculty(db))
    _run(db.courses.insert_one({"course_code": "LEGACY1", "faculty_id": str(faculty_oid)}))

    r = client.request("DELETE", f"/faculty/{faculty_oid}", headers=admin)
    assert r.status_code == 409
    assert _run(db.faculty.find_one({"_id": faculty_oid})) is not None


# ===========================================================================
# Timetable deletion — generated schedules
# ===========================================================================


def test_delete_timetable_blocked_by_generated_schedule(client, admin, db):
    tt = _run(_make_timetable(db))
    _run(db.generated_schedules.insert_one({"timetable_id": tt, "sessions": []}))

    r = client.request("DELETE", f"/timetable/{tt}", headers=admin)
    assert r.status_code == 409
    assert _run(db.timetables.find_one({"_id": tt})) is not None


def test_delete_timetable_without_dependents_succeeds(client, admin, db):
    tt = _run(_make_timetable(db))
    r = client.request("DELETE", f"/timetable/{tt}", headers=admin)
    assert r.status_code == 200
    assert _run(db.timetables.find_one({"_id": tt})) is None


def test_delete_unknown_timetable_is_404(client, admin):
    assert (
        client.request("DELETE", f"/timetable/{ObjectId()}", headers=admin).status_code
        == 404
    )


# ===========================================================================
# Lesson-plan deletion — generated schedules
# ===========================================================================


def test_delete_lesson_plan_blocked_by_generated_schedule(client, admin, db):
    lp = _run(_make_lesson_plan(db))
    _run(db.generated_schedules.insert_one({"lesson_plan_id": lp, "sessions": []}))

    r = client.request("DELETE", f"/lesson-plan/{lp}", headers=admin)
    assert r.status_code == 409
    assert _run(db.lesson_plans.find_one({"_id": lp})) is not None


def test_delete_lesson_plan_without_dependents_succeeds(client, admin, db):
    lp = _run(_make_lesson_plan(db))
    r = client.request("DELETE", f"/lesson-plan/{lp}", headers=admin)
    assert r.status_code == 200
    assert _run(db.lesson_plans.find_one({"_id": lp})) is None


def test_delete_malformed_lesson_plan_id_is_400(client, admin):
    # The established lesson-plan contract maps a malformed id to 400.
    assert (
        client.request("DELETE", "/lesson-plan/not-an-id", headers=admin).status_code
        == 400
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
