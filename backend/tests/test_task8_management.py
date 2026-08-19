"""Task #8 (Prompt 1) — management/API + resource-level authorization tests.

Covers the Course / Academic-Calendar / Timetable / Syllabus / Lesson-Plan
management endpoints and the Task #8 ownership authorization model
(``app.auth.resource_access``), exercised through FastAPI's ``TestClient``
against an in-memory ``mongomock_motor`` database with real Bearer JWTs.

Scope of this file (deliberately focused on Task #8):

  * Course CRUD + role gating + faculty read-scoping + dependency protection.
  * Academic-calendar CRUD + role gating (management is admin/hod only).
  * Timetable read authorization while preserving period functionality.
  * Syllabus list/get + delete dependency protection + authorization.
  * Lesson-plan list/get/update/delete + authorization.
  * Cross-faculty / cross-course access denial.
  * admin/HOD (manager) vs faculty permission split per the existing role model.
  * Dependency protection so a delete never silently orphans schedules,
    timetables, lesson plans, or syllabi.
  * ``structured_plan`` remains the canonical lesson-plan source and is not
    replaced by the flat ``lesson_plan`` text on update or on generation.

The suite mirrors the established style (see ``tests/test_auth_security.py``
and ``tests/test_export_service.py``): synchronous tests drive the ASGI app via
``TestClient`` while seeding runs on a short-lived loop through ``_run``.
"""

import asyncio

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import app.database.mongodb as mongodb
from app.api.v1.academic_calendar import router as calendar_router
from app.api.v1.course import router as course_router
from app.api.v1.lesson_plan import router as lesson_router
from app.api.v1.syllabus import router as syllabus_router
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
    app.include_router(course_router)
    app.include_router(syllabus_router)
    app.include_router(lesson_router)
    app.include_router(timetable_router)
    app.include_router(calendar_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


async def _make_user(db, role, email):
    uid = ObjectId()
    await db.users.insert_one(
        {
            "_id": uid,
            "name": role.title(),
            "email": email,
            "role": role,
            "department": "CSE",
        }
    )
    return uid


async def _make_faculty(db, email, faculty_id, name="Faculty"):
    # ``resolve_faculty_for_user`` matches by ``email.strip().lower()``.
    res = await db.faculty.insert_one(
        {
            "faculty_id": faculty_id,
            "name": name,
            "email": email.lower(),
            "department": "CSE",
            "designation": "Professor",
        }
    )
    return res.inserted_id


async def _make_course(db, faculty_oid, code, semester=1):
    res = await db.courses.insert_one(
        {
            "course_code": code.upper(),
            "course_name": f"Course {code}",
            "department": "CSE",
            "semester": semester,
            "credits": 4,
            "faculty_id": faculty_oid,
        }
    )
    return res.inserted_id


def _hdr(uid, role, email):
    token = create_access_token({"sub": str(uid), "role": role, "email": email})
    return {"Authorization": f"Bearer {token}"}


def _structured_plan(title="Intro to CS"):
    return {
        "course_title": title,
        "course_objectives": ["Understand basics"],
        "learning_outcomes": [
            {"outcome_id": "CO1", "description": "Explain X", "bloom_level": "Understand"}
        ],
        "units": [
            {
                "unit_number": 1,
                "unit_title": "Fundamentals",
                "topics": [
                    {
                        "topic_id": "U1-T1",
                        "topic": "Topic Alpha",
                        "estimated_hours": 2,
                    },
                    {
                        "topic_id": "U1-T2",
                        "topic": "Topic Beta",
                        "estimated_hours": 1,
                    },
                ],
            }
        ],
    }


class World:
    """Small fixed world: an admin, an HOD, and two independent faculty."""

    def __init__(self, data):
        self.__dict__.update(data)


@pytest.fixture()
def world(db):
    admin_email = "admin@example.com"
    hod_email = "hod@example.com"
    a_email = "faculty.a@example.com"
    b_email = "faculty.b@example.com"

    admin_uid = _run(_make_user(db, "admin", admin_email))
    hod_uid = _run(_make_user(db, "hod", hod_email))
    a_uid = _run(_make_user(db, "faculty", a_email))
    b_uid = _run(_make_user(db, "faculty", b_email))

    a_fac = _run(_make_faculty(db, a_email, "FAC-A"))
    b_fac = _run(_make_faculty(db, b_email, "FAC-B"))

    a_course = _run(_make_course(db, a_fac, "CSA101"))
    b_course = _run(_make_course(db, b_fac, "CSB201"))

    return World(
        {
            "admin": _hdr(admin_uid, "admin", admin_email),
            "hod": _hdr(hod_uid, "hod", hod_email),
            "fa": _hdr(a_uid, "faculty", a_email),
            "fb": _hdr(b_uid, "faculty", b_email),
            "a_fac": a_fac,
            "b_fac": b_fac,
            "a_course": a_course,
            "b_course": b_course,
        }
    )


# ===========================================================================
# Course CRUD + authorization
# ===========================================================================


def test_admin_can_create_course(client, world, db):
    r = client.post(
        "/course/",
        headers=world.admin,
        json={
            "course_code": "CS999",
            "course_name": "New Course",
            "department": "CSE",
            "semester": 1,
            "credits": 3,
            "faculty_id": str(world.a_fac),
        },
    )
    assert r.status_code == 200
    assert "course_id" in r.json()


def test_hod_can_create_course(client, world):
    r = client.post(
        "/course/",
        headers=world.hod,
        json={
            "course_code": "CS888",
            "course_name": "HOD Course",
            "department": "CSE",
            "semester": 1,
            "credits": 3,
            "faculty_id": str(world.a_fac),
        },
    )
    assert r.status_code == 200


def test_faculty_cannot_create_course(client, world):
    r = client.post(
        "/course/",
        headers=world.fa,
        json={
            "course_code": "CS777",
            "course_name": "Forbidden",
            "department": "CSE",
            "semester": 1,
            "credits": 3,
            "faculty_id": str(world.a_fac),
        },
    )
    assert r.status_code == 403


def test_create_course_with_unknown_faculty_is_400(client, world):
    r = client.post(
        "/course/",
        headers=world.admin,
        json={
            "course_code": "CS555",
            "course_name": "Bad Faculty",
            "department": "CSE",
            "semester": 1,
            "credits": 3,
            "faculty_id": str(ObjectId()),
        },
    )
    assert r.status_code == 400


def test_course_list_is_scoped_for_faculty_and_open_for_admin(client, world):
    admin_codes = {c["course_code"] for c in client.get("/course/", headers=world.admin).json()}
    assert {"CSA101", "CSB201"}.issubset(admin_codes)

    a_courses = client.get("/course/", headers=world.fa).json()
    a_codes = {c["course_code"] for c in a_courses}
    assert a_codes == {"CSA101"}  # faculty A sees only their own course


def test_faculty_can_read_own_course(client, world):
    r = client.get(f"/course/{world.a_course}", headers=world.fa)
    assert r.status_code == 200
    assert r.json()["course_code"] == "CSA101"


def test_faculty_cannot_read_other_faculty_course(client, world):
    # Cross-course access denial: faculty A may not read faculty B's course.
    r = client.get(f"/course/{world.b_course}", headers=world.fa)
    assert r.status_code == 403


def test_admin_can_read_any_course(client, world):
    assert client.get(f"/course/{world.b_course}", headers=world.admin).status_code == 200


def test_get_unknown_course_is_404(client, world):
    assert client.get(f"/course/{ObjectId()}", headers=world.admin).status_code == 404


def test_get_malformed_course_id_is_400(client, world):
    assert client.get("/course/not-an-id", headers=world.admin).status_code == 400


def test_admin_can_update_course_faculty_cannot(client, world):
    body = {
        "course_name": "Renamed",
        "department": "CSE",
        "semester": 1,
        "credits": 5,
        "faculty_id": str(world.a_fac),
    }
    assert client.put(f"/course/{world.a_course}", headers=world.admin, json=body).status_code == 200
    assert client.put(f"/course/{world.a_course}", headers=world.fa, json=body).status_code == 403


def test_delete_course_without_dependencies(client, world, db):
    fresh = _run(_make_course(db, world.a_fac, "CSX321"))
    assert client.delete(f"/course/{fresh}", headers=world.admin).status_code == 200
    assert _run(db.courses.find_one({"_id": fresh})) is None


def test_delete_unknown_course_is_404(client, world):
    assert client.delete(f"/course/{ObjectId()}", headers=world.admin).status_code == 404


@pytest.mark.parametrize(
    "collection,doc_factory",
    [
        ("timetables", lambda cid: {"faculty_id": ObjectId(), "course_id": cid, "semester": 1, "schedule": []}),
        ("syllabi", lambda cid: {"course_id": cid, "filename": "s.pdf", "text": "x"}),
        ("lesson_plans", lambda cid: {"course_id": cid, "lesson_plan": "t", "structured_plan": {}}),
        ("generated_schedules", lambda cid: {"course_id": cid, "sessions": []}),
    ],
)
def test_delete_course_blocked_by_each_dependent(client, world, db, collection, doc_factory):
    # Dependency protection: a course referenced by a timetable / syllabus /
    # lesson plan / generated schedule cannot be deleted (409), so nothing is
    # ever silently orphaned.
    course_oid = _run(_make_course(db, world.a_fac, f"CSDEP{collection[:3].upper()}"))
    _run(db[collection].insert_one(doc_factory(course_oid)))

    r = client.delete(f"/course/{course_oid}", headers=world.admin)
    assert r.status_code == 409
    # The course must still exist (delete was refused, not partially applied).
    assert _run(db.courses.find_one({"_id": course_oid})) is not None


# ===========================================================================
# Academic Calendar CRUD + authorization
# ===========================================================================


def _calendar_payload(**overrides):
    payload = {
        "academic_year": "2026-2027",
        "semester": 1,
        "semester_start": "2026-06-01",
        "semester_end": "2026-11-30",
        "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    }
    payload.update(overrides)
    return payload


def test_admin_can_create_calendar_faculty_cannot(client, world):
    assert client.post("/calendar/", headers=world.admin, json=_calendar_payload()).status_code == 200
    assert (
        client.post(
            "/calendar/", headers=world.fa, json=_calendar_payload(academic_year="2030-2031")
        ).status_code
        == 403
    )


def test_hod_can_create_calendar(client, world):
    assert (
        client.post(
            "/calendar/", headers=world.hod, json=_calendar_payload(academic_year="2028-2029")
        ).status_code
        == 200
    )


def test_any_authenticated_user_can_list_calendars(client, world):
    client.post("/calendar/", headers=world.admin, json=_calendar_payload())
    r = client.get("/calendar/", headers=world.fa)
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_calendar_update_and_delete_are_manager_only(client, world):
    created = client.post("/calendar/", headers=world.admin, json=_calendar_payload()).json()
    cal_id = created["calendar_id"]

    upd = {"holidays": [{"date": "2026-08-15", "name": "Independence Day"}]}
    assert client.put(f"/calendar/{cal_id}", headers=world.fa, json=upd).status_code == 403
    assert client.put(f"/calendar/{cal_id}", headers=world.admin, json=upd).status_code == 200

    assert client.delete(f"/calendar/{cal_id}", headers=world.fa).status_code == 403
    assert client.delete(f"/calendar/{cal_id}", headers=world.admin).status_code == 200


def test_get_unknown_calendar_is_404(client, world):
    assert client.get(f"/calendar/{ObjectId()}", headers=world.admin).status_code == 404


# ===========================================================================
# Timetable authorization (period functionality preserved)
# ===========================================================================


async def _seed_timetable(db, faculty_oid, course_oid, semester=1):
    res = await db.timetables.insert_one(
        {
            "faculty_id": faculty_oid,
            "course_id": course_oid,
            "semester": semester,
            "schedule": [
                {"day": "Monday", "period_start": 1, "period_end": 2, "subject": "Lecture"},
                {"day": "Wednesday", "period_start": 5, "period_end": 7, "subject": "Lab"},
            ],
        }
    )
    return res.inserted_id


def test_faculty_reads_own_timetable_with_periods_preserved(client, world, db):
    tt = _run(_seed_timetable(db, world.a_fac, world.a_course))
    r = client.get(f"/timetable/{tt}", headers=world.fa)
    assert r.status_code == 200
    schedule = r.json()["schedule"]
    # Period-based functionality (Task #4) must survive the Task #8 auth layer.
    assert schedule[0]["period_start"] == 1 and schedule[0]["period_end"] == 2
    assert schedule[1]["period_start"] == 5 and schedule[1]["period_end"] == 7


def test_faculty_cannot_read_other_faculty_timetable(client, world, db):
    tt = _run(_seed_timetable(db, world.a_fac, world.a_course))
    assert client.get(f"/timetable/{tt}", headers=world.fb).status_code == 403


def test_admin_reads_any_timetable(client, world, db):
    tt = _run(_seed_timetable(db, world.a_fac, world.a_course))
    assert client.get(f"/timetable/{tt}", headers=world.admin).status_code == 200


def test_timetable_list_is_scoped_for_faculty(client, world, db):
    _run(_seed_timetable(db, world.a_fac, world.a_course))
    _run(_seed_timetable(db, world.b_fac, world.b_course))

    a_list = client.get("/timetable/", headers=world.fa).json()
    assert len(a_list) == 1
    assert all(t["faculty_id"] == str(world.a_fac) for t in a_list)

    assert len(client.get("/timetable/", headers=world.admin).json()) == 2


def test_timetable_management_is_manager_only(client, world, db):
    tt = _run(_seed_timetable(db, world.a_fac, world.a_course))
    # Faculty (even the owner) cannot manage; management stays admin/hod only.
    assert client.put(f"/timetable/{tt}", headers=world.fa, json={"semester": 2}).status_code == 403
    assert client.request("DELETE", f"/timetable/{tt}", headers=world.fa).status_code == 403


# ===========================================================================
# Syllabus list/get/delete + dependency protection + authorization
# ===========================================================================


async def _seed_syllabus(db, course_oid, filepath=None):
    res = await db.syllabi.insert_one(
        {
            "course_id": course_oid,
            "filename": "syllabus.pdf",
            "filepath": filepath,
            "original_filename": "orig.pdf",
            "text": "Some syllabus text",
            "extraction_method": "text",
        }
    )
    return res.inserted_id


def test_syllabus_list_scoped_for_faculty(client, world, db):
    _run(_seed_syllabus(db, world.a_course))
    _run(_seed_syllabus(db, world.b_course))

    a_list = client.get("/syllabus/", headers=world.fa).json()
    assert all(s["course_id"] == str(world.a_course) for s in a_list)
    assert len(a_list) == 1

    assert len(client.get("/syllabus/", headers=world.admin).json()) == 2


def test_faculty_can_read_own_syllabus_not_others(client, world, db):
    syl_a = _run(_seed_syllabus(db, world.a_course))
    syl_b = _run(_seed_syllabus(db, world.b_course))

    assert client.get(f"/syllabus/{syl_a}", headers=world.fa).status_code == 200
    # Cross-course denial for a syllabus belonging to another faculty's course.
    assert client.get(f"/syllabus/{syl_b}", headers=world.fa).status_code == 403


def test_syllabus_response_never_leaks_filepath(client, world, db):
    syl = _run(_seed_syllabus(db, world.a_course, filepath="/srv/uploads/secret.pdf"))
    body = client.get(f"/syllabus/{syl}", headers=world.admin).json()
    assert "filepath" not in body


def test_syllabus_delete_is_manager_only(client, world, db):
    syl = _run(_seed_syllabus(db, world.a_course))
    assert client.request("DELETE", f"/syllabus/{syl}", headers=world.fa).status_code == 403


def test_syllabus_delete_blocked_by_dependent_lesson_plan(client, world, db):
    # Dependency protection: a syllabus with a generated lesson plan cannot be
    # deleted (409), so the lesson plan is never orphaned onto a missing file.
    syl = _run(_seed_syllabus(db, world.a_course))
    _run(db.lesson_plans.insert_one({"course_id": world.a_course, "syllabus_id": syl, "lesson_plan": "t"}))

    r = client.delete(f"/syllabus/{syl}", headers=world.admin)
    assert r.status_code == 409
    assert _run(db.syllabi.find_one({"_id": syl})) is not None


def test_syllabus_delete_without_dependents_succeeds(client, world, db):
    syl = _run(_seed_syllabus(db, world.a_course))
    assert client.delete(f"/syllabus/{syl}", headers=world.admin).status_code == 200
    assert _run(db.syllabi.find_one({"_id": syl})) is None


def test_delete_unknown_syllabus_is_404(client, world):
    assert client.delete(f"/syllabus/{ObjectId()}", headers=world.admin).status_code == 404


# ===========================================================================
# Lesson-plan list/get/update/delete + authorization
# ===========================================================================


async def _seed_lesson_plan(db, course_oid, structured=True, text="Topic Alpha\nTopic Beta"):
    res = await db.lesson_plans.insert_one(
        {
            "course_id": course_oid,
            "syllabus_id": ObjectId(),
            "lesson_plan": text,
            "structured_plan": _structured_plan() if structured else None,
        }
    )
    return res.inserted_id


def test_lesson_plan_list_scoped_for_faculty(client, world, db):
    _run(_seed_lesson_plan(db, world.a_course))
    _run(_seed_lesson_plan(db, world.b_course))

    a_list = client.get("/lesson-plan/", headers=world.fa).json()
    assert len(a_list) == 1
    assert all(lp["course_id"] == str(world.a_course) for lp in a_list)

    assert len(client.get("/lesson-plan/", headers=world.admin).json()) == 2


def test_faculty_reads_own_lesson_plan_not_others(client, world, db):
    lp_a = _run(_seed_lesson_plan(db, world.a_course))
    lp_b = _run(_seed_lesson_plan(db, world.b_course))

    assert client.get(f"/lesson-plan/{lp_a}", headers=world.fa).status_code == 200
    # Cross-faculty denial.
    assert client.get(f"/lesson-plan/{lp_b}", headers=world.fa).status_code == 403


def test_get_unknown_lesson_plan_is_404(client, world):
    assert client.get(f"/lesson-plan/{ObjectId()}", headers=world.admin).status_code == 404


def test_get_malformed_lesson_plan_id_is_400(client, world):
    # Regression guard: the Task #8 authorization wrapper must keep the
    # documented 400-on-malformed contract (not silently downgrade to 404).
    assert client.get("/lesson-plan/not-an-id", headers=world.admin).status_code == 400


def test_faculty_can_update_own_lesson_plan(client, world, db):
    lp = _run(_seed_lesson_plan(db, world.a_course))
    r = client.put(
        f"/lesson-plan/{lp}",
        headers=world.fa,
        json={"lesson_plan": "Rewritten topic list line one"},
    )
    assert r.status_code == 200


def test_faculty_cannot_update_other_faculty_lesson_plan(client, world, db):
    lp_b = _run(_seed_lesson_plan(db, world.b_course))
    r = client.put(
        f"/lesson-plan/{lp_b}",
        headers=world.fa,
        json={"lesson_plan": "Malicious cross-faculty edit attempt"},
    )
    assert r.status_code == 403


def test_lesson_plan_delete_is_manager_only(client, world, db):
    lp = _run(_seed_lesson_plan(db, world.a_course))
    # Faculty (even the owner) cannot delete; delete stays admin/hod only.
    assert client.request("DELETE", f"/lesson-plan/{lp}", headers=world.fa).status_code == 403
    assert client.request("DELETE", f"/lesson-plan/{lp}", headers=world.admin).status_code == 200
    assert _run(db.lesson_plans.find_one({"_id": lp})) is None


def test_delete_unknown_lesson_plan_is_404(client, world):
    assert client.request("DELETE", f"/lesson-plan/{ObjectId()}", headers=world.admin).status_code == 404


# ===========================================================================
# structured_plan is the canonical lesson-plan source
# ===========================================================================


def test_update_preserves_canonical_structured_plan(client, world, db):
    """Updating the flat ``lesson_plan`` text must NOT touch ``structured_plan``.

    The structured plan is the canonical source consumed by the scheduler /
    exports; the flat text is only a backward-compatible convenience mirror.
    """
    original_structured = _structured_plan()
    lp = _run(_seed_lesson_plan(db, world.a_course))
    stored_before = _run(db.lesson_plans.find_one({"_id": lp}))
    assert stored_before["structured_plan"] == original_structured

    r = client.put(
        f"/lesson-plan/{lp}",
        headers=world.admin,
        json={"lesson_plan": "Completely different flat text override here"},
    )
    assert r.status_code == 200

    stored_after = _run(db.lesson_plans.find_one({"_id": lp}))
    # Flat text updated ...
    assert stored_after["lesson_plan"] == "Completely different flat text override here"
    # ... structured plan untouched (still canonical).
    assert stored_after["structured_plan"] == original_structured


def test_generation_stores_structured_plan_as_canonical(db, monkeypatch):
    """Generation persists the structured plan and derives the flat text from
    it — the flat ``lesson_plan`` never becomes the source of truth.
    """
    from app.schemas.lesson_plan_schema import LessonPlanAIOutput
    from app.services import lesson_plan_service as lps

    course_oid = _run(_make_course(db, ObjectId(), "CSGEN1"))
    syllabus_id = _run(
        db.syllabi.insert_one(
            {"course_id": course_oid, "filename": "s.pdf", "text": "syllabus body"}
        )
    ).inserted_id

    plan = LessonPlanAIOutput.model_validate(_structured_plan("Generated Title"))

    async def _fake_generate(text):  # noqa: ANN001 - test stub
        assert text == "syllabus body"
        return plan

    # Patch the AI call only; ``structured_to_topic_text`` stays real so we
    # verify the flat text is DERIVED from the structured plan.
    monkeypatch.setattr(lps, "generate_lesson_plan", _fake_generate)

    result = _run(lps.generate_and_save_lesson_plan(str(syllabus_id)))

    expected_flat = "Topic Alpha\nTopic Beta"
    assert result["lesson_plan"] == expected_flat
    assert result["structured_plan"] == plan.model_dump(mode="json")

    stored = _run(db.lesson_plans.find_one({"_id": ObjectId(result["lesson_plan_id"])}))
    assert stored["structured_plan"] == plan.model_dump(mode="json")
    assert stored["lesson_plan"] == expected_flat
    # course_id is inherited from the parent syllabus as an ObjectId.
    assert stored["course_id"] == course_oid


# ===========================================================================
# Every management surface still requires authentication
# ===========================================================================


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/course/"),
        ("GET", "/calendar/"),
        ("GET", "/timetable/"),
        ("GET", "/syllabus/"),
        ("GET", "/lesson-plan/"),
    ],
)
def test_endpoints_require_jwt(client, method, path):
    assert client.request(method, path).status_code == 401
