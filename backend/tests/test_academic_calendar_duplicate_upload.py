"""Duplicate academic-calendar upload handling.

Reproduces and locks down the real production bug: uploading the SAME actual
ACE academic calendar (same ``academic_year`` + ``semester``) a second time
used to bubble the raw ``pymongo.errors.DuplicateKeyError`` out of the
``POST /calendar/upload`` endpoint as an unhandled **HTTP 500** with a full
traceback.

Required behaviour, verified here:

  * First upload of a new calendar still succeeds (HTTP 200 + ``calendar_id`` +
    ``extraction_status``) — unchanged.
  * A duplicate ``academic_year`` + ``semester`` upload now returns a controlled
    **HTTP 409 Conflict** with a clean message.
  * The duplicate does NOT create a second MongoDB document.
  * The 409 response never exposes MongoDB collection names, index names, raw
    pymongo errors, stack traces, or other database internals.
  * A different academic year / semester can still be created.
  * A concurrent/race duplicate insert is handled safely (the unique index is
    the final protection, and the raced request maps to the domain error).

The unique index ``uniq_calendar_year_semester`` must remain the last line of
defence — these tests do NOT remove or weaken it; they build it on the
in-memory ``mongomock_motor`` database exactly like production does.
"""

import asyncio

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from pymongo.errors import DuplicateKeyError

import app.database.mongodb as mongodb
from app.api.v1.academic_calendar import router as calendar_router
from app.auth.dependencies import get_current_user, require_roles
from app.schemas.academic_calendar_schema import AcademicCalendarCreate
from app.services.academic_calendar_service import (
    CalendarAlreadyExistsError,
    _is_calendar_identity_conflict,
    create_pending_calendar,
)


def _run(coro):
    return asyncio.run(coro)


# --- Database double: mirrors the real unique index --------------------------


async def _make_db():
    """Return a fresh in-memory DB with the SAME unique calendar index as prod.

    Builds ``uniq_calendar_year_semester`` on (academic_year, semester) so the
    duplicate constraint is genuinely exercised, not simulated.
    """
    client = AsyncMongoMockClient()
    database = client["test_db"]
    await database.academic_calendar.create_index(
        [("academic_year", 1), ("semester", 1)],
        unique=True,
        name="uniq_calendar_year_semester",
    )
    return database


@pytest.fixture()
def db(monkeypatch):
    database = _run(_make_db())
    monkeypatch.setattr(mongodb, "database", database)
    return database


# --- Payload helpers ---------------------------------------------------------


def _base_kwargs(academic_year="2026-2027", semester=7, **overrides):
    kwargs = dict(
        academic_year=academic_year,
        semester=semester,
        semester_start="2026-06-01",
        semester_end="2026-11-30",
        working_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    )
    kwargs.update(overrides)
    return kwargs


def _payload(**overrides):
    return AcademicCalendarCreate(**_base_kwargs(**overrides))


# --- API client: real upload route, auth + extraction stubbed ----------------


@pytest.fixture()
def client(db, monkeypatch):
    """A TestClient wired to the real ``/calendar`` router.

    Authentication and the CPU-heavy document extraction are stubbed so the
    test focuses purely on duplicate-upload handling. The extraction stub always
    yields the SAME calendar identity (2026-2027, Semester 7), i.e. the real ACE
    calendar the faculty already uploaded once.
    """
    app = FastAPI()
    app.include_router(calendar_router)

    # Bypass auth: accept any request as an admin user.
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test-admin",
        "role": "admin",
        "email": "admin@example.com",
    }

    async def _fake_process_calendar_document(filepath: str, filename: str):
        return {
            "calendar": _payload(),
            "raw_text": "ACE ACADEMIC CALENDAR 2026-2027 SEMESTER 7",
            "extraction_method": "pdf_text_layer",
        }

    # Patch the reference imported into the API module.
    import app.api.v1.academic_calendar as calendar_api

    monkeypatch.setattr(
        calendar_api,
        "process_calendar_document",
        _fake_process_calendar_document,
    )

    return TestClient(app)


def _upload(client):
    return client.post(
        "/calendar/upload",
        files={
            "file": (
                "ace_calendar_2026_2027_sem7.pdf",
                b"%PDF-1.4 fake pdf bytes",
                "application/pdf",
            )
        },
    )


# --- Service-layer: first upload succeeds ------------------------------------


def test_first_pending_calendar_upload_succeeds(db):
    calendar_id = _run(create_pending_calendar(_payload()))

    assert isinstance(calendar_id, str) and calendar_id
    assert _run(db.academic_calendar.count_documents({})) == 1
    stored = _run(
        db.academic_calendar.find_one(
            {"academic_year": "2026-2027", "semester": 7}
        )
    )
    assert stored is not None
    assert stored["status"] == "pending_review"


# --- Service-layer: duplicate raises the clean domain error ------------------


def test_duplicate_pending_calendar_raises_domain_error(db):
    _run(create_pending_calendar(_payload()))

    with pytest.raises(CalendarAlreadyExistsError) as excinfo:
        _run(create_pending_calendar(_payload()))

    # Clean, user-facing message; no DB internals.
    assert str(excinfo.value) == (
        "Academic calendar for 2026-2027 Semester 7 already exists."
    )
    # Still exactly one document — no duplicate was created.
    assert _run(db.academic_calendar.count_documents({})) == 1


# --- Service-layer: race-safe duplicate handling -----------------------------


def test_race_duplicate_insert_is_handled(db, monkeypatch):
    """Simulate two requests passing the pre-check and racing to insert.

    We force ``find_one`` to report "no existing calendar" (as it would for the
    losing request that read before the winner committed), so the code path that
    reaches ``insert_one`` and hits the unique index is exercised directly.
    The unique index remains the final protection.
    """
    _run(create_pending_calendar(_payload()))
    assert _run(db.academic_calendar.count_documents({})) == 1

    async def _pretend_absent(*args, **kwargs):
        return None

    monkeypatch.setattr(db.academic_calendar, "find_one", _pretend_absent)

    with pytest.raises(CalendarAlreadyExistsError):
        _run(create_pending_calendar(_payload()))

    # The unique index blocked the second insert: still exactly one document.
    assert _run(db.academic_calendar.count_documents({})) == 1


def test_unrelated_duplicate_key_error_is_not_masked():
    """A duplicate on some OTHER index must NOT be mislabelled as a calendar
    identity conflict (we never blanket-catch every duplicate)."""
    other = DuplicateKeyError(
        "E11000 duplicate key error",
        details={"keyPattern": {"course_code": 1}},
    )
    assert _is_calendar_identity_conflict(other) is False

    identity = DuplicateKeyError(
        "E11000 duplicate key error",
        details={"keyPattern": {"academic_year": 1, "semester": 1}},
    )
    assert _is_calendar_identity_conflict(identity) is True


# --- Service-layer: other identities still allowed ---------------------------


def test_different_academic_year_still_allowed(db):
    _run(create_pending_calendar(_payload(academic_year="2026-2027", semester=7)))
    _run(create_pending_calendar(_payload(academic_year="2027-2028", semester=7)))

    assert _run(db.academic_calendar.count_documents({})) == 2


def test_different_semester_still_allowed(db):
    _run(create_pending_calendar(_payload(academic_year="2026-2027", semester=7)))
    _run(
        create_pending_calendar(
            _payload(
                academic_year="2026-2027",
                semester=8,
                semester_start="2027-01-01",
                semester_end="2027-05-31",
            )
        )
    )

    assert _run(db.academic_calendar.count_documents({})) == 2


# --- API-layer: first upload 200, duplicate 409 ------------------------------


def test_api_first_upload_returns_200_with_calendar_id(client, db):
    response = _upload(client)

    assert response.status_code == 200
    body = response.json()
    assert body["calendar_id"]
    assert body["extraction_status"] == "needs_review"
    assert body["calendar"]["academic_year"] == "2026-2027"
    assert body["calendar"]["semester"] == 7
    assert _run(db.academic_calendar.count_documents({})) == 1


def test_api_duplicate_upload_returns_409(client, db):
    first = _upload(client)
    assert first.status_code == 200

    duplicate = _upload(client)
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Academic calendar for 2026-2027 Semester 7 already exists."
    }


def test_api_duplicate_upload_does_not_create_second_document(client, db):
    assert _upload(client).status_code == 200
    assert _upload(client).status_code == 409

    assert _run(db.academic_calendar.count_documents({})) == 1


def test_api_duplicate_upload_does_not_leak_database_internals(client, db):
    assert _upload(client).status_code == 200
    duplicate = _upload(client)
    assert duplicate.status_code == 409

    detail = duplicate.json()["detail"]
    leak_markers = [
        "academic_calendar",        # collection name
        "uniq_calendar_year_semester",  # index name
        "E11000",                    # raw mongo duplicate-key code
        "DuplicateKeyError",         # pymongo exception class
        "pymongo",
        "Traceback",
        "keyPattern",
        "lesson_plan_db",            # database name
    ]
    for marker in leak_markers:
        assert marker not in detail, f"response leaked DB internal: {marker!r}"
