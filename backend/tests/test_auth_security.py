"""Security regression tests for public registration and DB-backed JWT users."""

import asyncio

import pytest
from bson import ObjectId
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import app.database.mongodb as mongodb
from app.api.v1.auth import router as auth_router
from app.auth.dependencies import get_current_user, require_roles
from app.auth.jwt import create_access_token


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    monkeypatch.setattr(mongodb, "database", database)
    return database


@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(auth_router)

    @app.get("/authenticated")
    async def authenticated(user: dict = Depends(get_current_user)):
        return user

    @app.get("/admin-only", dependencies=[Depends(require_roles("admin", "hod"))])
    async def admin_only():
        return {"ok": True}

    return TestClient(app)


def _token(user_id: ObjectId, role: str = "faculty", email: str = "user@example.com"):
    return {
        "Authorization": "Bearer "
        + create_access_token({"sub": str(user_id), "role": role, "email": email})
    }


async def _insert_user(db, *, role="faculty", email="user@example.com", password="hash"):
    user_id = ObjectId()
    await db.users.insert_one(
        {
            "_id": user_id,
            "name": "Current User",
            "email": email,
            "password": password,
            "role": role,
            "department": "CSE",
        }
    )
    return user_id


def test_public_registration_without_role_creates_faculty(client, db):
    response = client.post(
        "/auth/register",
        json={"name": "Faculty User", "email": "faculty1@example.com", "password": "secret1", "department": "CSE"},
    )

    assert response.status_code == 200
    user = _run(db.users.find_one({"email": "faculty1@example.com"}))
    assert user["role"] == "faculty"


def test_public_registration_with_faculty_role_creates_faculty(client, db):
    response = client.post(
        "/auth/register",
        json={"name": "Faculty User", "email": "faculty2@example.com", "password": "secret1", "role": "faculty", "department": "CSE"},
    )

    assert response.status_code == 200
    user = _run(db.users.find_one({"email": "faculty2@example.com"}))
    assert user["role"] == "faculty"


@pytest.mark.parametrize("role", ["admin", "hod"])
def test_public_registration_rejects_privileged_roles(client, db, role):
    response = client.post(
        "/auth/register",
        json={"name": "Privileged User", "email": f"{role}@example.com", "password": "secret1", "role": role, "department": "CSE"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Public registration can only create faculty users"
    assert _run(db.users.find_one({"email": f"{role}@example.com"})) is None


def test_existing_user_jwt_authenticates_from_database(client, db):
    user_id = _run(_insert_user(db))

    response = client.get("/authenticated", headers=_token(user_id))

    assert response.status_code == 200
    assert response.json()["id"] == str(user_id)
    assert response.json()["role"] == "faculty"


def test_deleted_user_jwt_is_rejected(client, db):
    user_id = _run(_insert_user(db))
    headers = _token(user_id)
    _run(db.users.delete_one({"_id": user_id}))

    response = client.get("/authenticated", headers=headers)

    assert response.status_code == 401


def test_current_database_role_controls_authorization(client, db):
    user_id = _run(_insert_user(db, role="faculty"))
    headers = _token(user_id, role="faculty")
    _run(db.users.update_one({"_id": user_id}, {"$set": {"role": "hod"}}))

    response = client.get("/admin-only", headers=headers)

    assert response.status_code == 200


def test_stale_privileged_jwt_does_not_bypass_current_database_role(client, db):
    user_id = _run(_insert_user(db, role="admin"))
    headers = _token(user_id, role="admin")
    _run(db.users.update_one({"_id": user_id}, {"$set": {"role": "faculty"}}))

    response = client.get("/admin-only", headers=headers)

    assert response.status_code == 403


def test_profile_returns_safe_current_database_user(client, db):
    user_id = _run(_insert_user(db, role="faculty", email="old@example.com", password="secret-hash"))
    _run(
        db.users.update_one(
            {"_id": user_id},
            {"$set": {"name": "Updated User", "email": "current@example.com", "role": "hod"}},
        )
    )

    response = client.get("/auth/profile", headers=_token(user_id, role="faculty", email="old@example.com"))

    assert response.status_code == 200
    user = response.json()["user"]
    assert user == {
        "id": str(user_id), "name": "Updated User", "email": "current@example.com",
        "role": "hod", "department": "CSE",
    }
    assert "password" not in user


def test_missing_token_is_rejected(client):
    # No Authorization header at all -> 401 (never 403 from HTTPBearer).
    assert client.get("/authenticated").status_code == 401


def test_malformed_token_is_rejected(client):
    # A Bearer value that is not a valid JWT -> 401 (JWTError path).
    response = client.get(
        "/authenticated",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401


def test_token_with_invalid_user_id_is_rejected(client, db):
    # A well-formed JWT whose ``sub`` is not a valid ObjectId -> 401 (the
    # subject can never resolve to a real database user).
    headers = {
        "Authorization": "Bearer "
        + create_access_token({"sub": "not-an-object-id", "role": "faculty", "email": "x@example.com"})
    }
    assert client.get("/authenticated", headers=headers).status_code == 401


def test_token_with_unknown_user_id_is_rejected(client, db):
    # A syntactically valid ObjectId that does not exist in the users
    # collection -> 401 (DB-backed validation rejects it).
    headers = _token(ObjectId(), role="faculty")
    assert client.get("/authenticated", headers=headers).status_code == 401


def test_existing_login_still_returns_usable_bearer_token(client, db):
    # Use the public registration flow to obtain a real bcrypt hash for this user.
    response = client.post(
        "/auth/register",
        json={"name": "Login User", "email": "real-login@example.com", "password": "secret1", "department": "CSE"},
    )
    assert response.status_code == 200

    login = client.post("/auth/login", json={"email": "real-login@example.com", "password": "secret1"})
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"

    authenticated = client.get(
        "/authenticated", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert authenticated.status_code == 200
    assert authenticated.json()["role"] == "faculty"
