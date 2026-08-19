"""Tests for MongoDB startup health + index initialization (Task #8.2).

Covers:
  * ``ping_database`` succeeds against a reachable server and raises the
    controlled ``DatabaseUnavailableError`` when the ping fails (no driver
    internals leaked).
  * ``init_indexes`` is idempotent (safe to run repeatedly) and preserves every
    unique index.
  * ``init_indexes`` fails CLEARLY (never deletes data) when pre-existing
    duplicate records would violate a new unique index.
  * ``/health`` reports 200 when the database is reachable and 503 when it is
    not — and never depends on Groq/OCR.

No real MongoDB, Groq or OCR is used; ``mongomock_motor`` backs the database
and failures are injected via monkeypatching.

Run: python -m pytest backend/tests/test_database_health.py -q
"""

import asyncio
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from pymongo.errors import PyMongoError

import app.database.mongodb as mongodb
from app.database.mongodb import (
    DatabaseUnavailableError,
    init_indexes,
    ping_database,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# ping_database
# ---------------------------------------------------------------------------

def test_ping_succeeds_against_reachable_server():
    client = AsyncMongoMockClient()
    assert _run(ping_database(client)) is True


def test_ping_failure_raises_controlled_error():
    class _BadAdmin:
        async def command(self, *_a, **_k):
            raise PyMongoError("server selection timeout: 10.0.0.5:27017 auth=secret")

    fake_client = types.SimpleNamespace(admin=_BadAdmin())

    with pytest.raises(DatabaseUnavailableError) as exc:
        _run(ping_database(fake_client))

    # The safe message must not leak host/credentials from the driver error.
    assert "secret" not in str(exc.value)
    assert "10.0.0.5" not in str(exc.value)


def test_ping_without_client_raises():
    with pytest.raises(DatabaseUnavailableError):
        _run(ping_database(None))


# ---------------------------------------------------------------------------
# init_indexes
# ---------------------------------------------------------------------------

def test_init_indexes_is_idempotent_and_creates_all():
    db = AsyncMongoMockClient()["idx_db"]

    _run(init_indexes(db))
    # Running again must be safe (idempotent) — no exception.
    _run(init_indexes(db))

    async def _names(coll):
        return {ix["name"] async for ix in db[coll].list_indexes()}

    assert "uniq_users_email" in _run(_names("users"))
    assert "uniq_faculty_faculty_id" in _run(_names("faculty"))
    assert "uniq_courses_course_code" in _run(_names("courses"))
    assert "uniq_calendar_year_semester" in _run(_names("academic_calendar"))


def test_unique_index_enforced_after_init():
    db = AsyncMongoMockClient()["idx_db2"]
    _run(init_indexes(db))

    async def _insert_dupes():
        await db.users.insert_one({"email": "dupe@example.com"})
        await db.users.insert_one({"email": "dupe@example.com"})

    with pytest.raises(PyMongoError):
        _run(_insert_dupes())


def test_init_indexes_fails_clearly_on_duplicate_legacy_data():
    db = AsyncMongoMockClient()["idx_db3"]

    async def _seed_and_init():
        # Duplicate faculty_id values that violate the intended unique index.
        await db.faculty.insert_one({"faculty_id": "FAC-1"})
        await db.faculty.insert_one({"faculty_id": "FAC-1"})
        await init_indexes(db)

    with pytest.raises(RuntimeError) as exc:
        _run(_seed_and_init())

    # Clear, controlled failure — no silent data deletion.
    assert "duplicate" in str(exc.value).lower()
    # Both offending records are still present (nothing was deleted).
    assert _run(db.faculty.count_documents({"faculty_id": "FAC-1"})) == 2


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------

def _health_client():
    # Import lazily so the settings/env are already stubbed by conftest.
    from app.main import app

    return TestClient(app)


def test_health_ok_when_database_reachable(monkeypatch):
    async def _ok(*_a, **_k):
        return True

    monkeypatch.setattr("app.main.ping_database", _ok)

    r = _health_client().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_health_degraded_when_database_unreachable(monkeypatch):
    async def _fail(*_a, **_k):
        raise DatabaseUnavailableError("Could not reach the database")

    monkeypatch.setattr("app.main.ping_database", _fail)

    r = _health_client().get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
