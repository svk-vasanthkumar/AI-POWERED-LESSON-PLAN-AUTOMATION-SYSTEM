"""Database Integrity tests.

Covers:
  - courses.faculty_id is stored as a native ObjectId for new records
  - a nonexistent faculty is rejected on course creation
  - duplicate course_code / faculty_id / user email are rejected
  - duplicate academic_year + semester is rejected
  - different academic_year (same semester) and same academic_year
    (different semester) are both allowed
  - index initialization succeeds and is safe to run repeatedly
  - legacy string faculty_id records still read without crashing

These tests exercise the service layer directly against an in-memory
``mongomock_motor`` database, mirroring the existing test-suite style.
"""

import asyncio

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

import app.database.mongodb as mongodb
from app.database.mongodb import init_indexes
from app.schemas.academic_calendar_schema import AcademicCalendarCreate
from app.schemas.course_schema import CourseCreate
from app.schemas.faculty_schema import FacultyCreate
from app.schemas.user_schema import UserRegister
from app.services.academic_calendar_service import create_calendar
from app.services.auth_service import register_user
from app.services.course_service import create_course
from app.services.faculty_service import create_faculty
from app.services.progress_service import _resolve_faculty


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    monkeypatch.setattr(mongodb, "database", database)
    return database


# --- helpers ---------------------------------------------------------------


async def _seed_faculty(db, faculty_id="FAC001", email="fac@example.com"):
    """Insert a faculty record directly and return its ObjectId."""
    result = await db.faculty.insert_one(
        {
            "faculty_id": faculty_id,
            "name": "Seed Faculty",
            "email": email,
            "department": "CSE",
            "designation": "Professor",
        }
    )
    return result.inserted_id


def _course_payload(faculty_id, course_code="CS101"):
    return CourseCreate(
        course_code=course_code,
        course_name="Intro to CS",
        department="CSE",
        semester=1,
        credits=4,
        faculty_id=str(faculty_id),
    )


def _calendar_payload(academic_year="2024-2025", semester=1):
    return AcademicCalendarCreate(
        academic_year=academic_year,
        semester=semester,
        semester_start="2024-06-01",
        semester_end="2024-11-30",
        working_days=["Monday", "Tuesday"],
        holidays=[],
        internal_exams=[],
    )


# --- ObjectId relationship -------------------------------------------------


def test_course_faculty_id_is_stored_as_object_id(db):
    faculty_oid = _run(_seed_faculty(db))

    course_id = _run(create_course(_course_payload(faculty_oid)))

    stored = _run(db.courses.find_one({"_id": ObjectId(course_id)}))
    assert isinstance(stored["faculty_id"], ObjectId)
    assert stored["faculty_id"] == faculty_oid


def test_nonexistent_faculty_is_rejected(db):
    payload = _course_payload(ObjectId())  # valid id, no such faculty

    with pytest.raises(ValueError, match="Faculty not found"):
        _run(create_course(payload))


def test_invalid_faculty_id_is_rejected(db):
    payload = _course_payload("not-an-object-id")

    # to_object_id raises an HTTPException (400) for malformed ids.
    with pytest.raises(Exception):
        _run(create_course(payload))


# --- Duplicate handling ----------------------------------------------------


def test_duplicate_course_code_is_rejected(db):
    faculty_oid = _run(_seed_faculty(db))
    _run(create_course(_course_payload(faculty_oid)))

    with pytest.raises(ValueError, match="Course already exists"):
        _run(create_course(_course_payload(faculty_oid)))


def test_duplicate_course_code_is_case_insensitive(db):
    # Preserves the existing uppercase normalization: cs101 collides with CS101.
    faculty_oid = _run(_seed_faculty(db))
    _run(create_course(_course_payload(faculty_oid, course_code="CS101")))

    with pytest.raises(ValueError, match="Course already exists"):
        _run(create_course(_course_payload(faculty_oid, course_code="cs101")))


def test_duplicate_faculty_id_is_rejected(db):
    payload = FacultyCreate(
        faculty_id="FAC999",
        name="Faculty One",
        email="f1@example.com",
        department="CSE",
        designation="Professor",
    )
    _run(create_faculty(payload))

    dup = FacultyCreate(
        faculty_id="FAC999",
        name="Faculty Two",
        email="f2@example.com",
        department="CSE",
        designation="Professor",
    )
    with pytest.raises(ValueError, match="Faculty ID already exists"):
        _run(create_faculty(dup))


def test_duplicate_user_email_is_rejected(db):
    payload = UserRegister(
        name="User One",
        email="dup@example.com",
        password="secret1",
        department="CSE",
    )
    _run(register_user(payload))

    dup = UserRegister(
        name="User Two",
        email="dup@example.com",
        password="secret2",
        department="CSE",
    )
    with pytest.raises(ValueError, match="Email already registered"):
        _run(register_user(dup))


# --- Academic calendar uniqueness ------------------------------------------


def test_duplicate_year_and_semester_is_rejected(db):
    _run(create_calendar(_calendar_payload("2024-2025", 1)))

    with pytest.raises(ValueError, match="Calendar already exists"):
        _run(create_calendar(_calendar_payload("2024-2025", 1)))


def test_same_semester_different_year_is_allowed(db):
    _run(create_calendar(_calendar_payload("2024-2025", 1)))
    # Different academic_year, same semester -> allowed.
    _run(create_calendar(_calendar_payload("2025-2026", 1)))

    assert _run(db.academic_calendar.count_documents({})) == 2


def test_same_year_different_semester_is_allowed(db):
    _run(create_calendar(_calendar_payload("2024-2025", 1)))
    # Same academic_year, different semester -> allowed.
    _run(create_calendar(_calendar_payload("2024-2025", 2)))

    assert _run(db.academic_calendar.count_documents({})) == 2


# --- Index initialization --------------------------------------------------


def test_index_initialization_succeeds(db):
    _run(init_indexes(db))

    users_indexes = _run(db.users.index_information())
    faculty_indexes = _run(db.faculty.index_information())
    courses_indexes = _run(db.courses.index_information())
    calendar_indexes = _run(db.academic_calendar.index_information())

    assert "uniq_users_email" in users_indexes
    assert "uniq_faculty_faculty_id" in faculty_indexes
    assert "uniq_courses_course_code" in courses_indexes
    assert "uniq_calendar_year_semester" in calendar_indexes


def test_repeated_index_initialization_is_safe(db):
    # Calling initialization multiple times must not raise.
    _run(init_indexes(db))
    _run(init_indexes(db))
    _run(init_indexes(db))

    courses_indexes = _run(db.courses.index_information())
    assert "uniq_courses_course_code" in courses_indexes


# --- Legacy compatibility --------------------------------------------------


def test_legacy_string_faculty_id_reads_do_not_crash(db):
    # Simulate an existing legacy course record whose faculty_id is a plain
    # string (the old inconsistent format) and confirm it reads back fine.
    _run(
        db.courses.insert_one(
            {
                "course_code": "LEG101",
                "course_name": "Legacy Course",
                "department": "CSE",
                "semester": 1,
                "credits": 3,
                "faculty_id": "FAC-LEGACY",
            }
        )
    )

    stored = _run(db.courses.find_one({"course_code": "LEG101"}))
    assert stored["faculty_id"] == "FAC-LEGACY"


def test_legacy_string_faculty_id_resolves_by_faculty_code(db):
    # The read helper must handle a legacy string faculty_id by falling back to
    # the custom faculty_id field instead of crashing.
    _run(_seed_faculty(db, faculty_id="FAC-LEGACY", email="legacy@example.com"))

    resolved = _run(_resolve_faculty(db, "FAC-LEGACY"))
    assert resolved is not None
    assert resolved["faculty_id"] == "FAC-LEGACY"
