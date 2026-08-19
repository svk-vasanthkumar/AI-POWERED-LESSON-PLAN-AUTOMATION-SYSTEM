"""Reusable authentication & role-based access control (RBAC) dependencies.

These build on top of the EXISTING JWT verification (`app.auth.jwt.verify_token`).
No token parsing logic is duplicated here.

The JWT payload created at login (`app.services.auth_service.login_user`) contains:
    - sub   -> user id (stringified ObjectId)
    - role  -> "admin" | "hod" | "faculty"
    - email -> user email

Passwords / password hashes are never placed in the token, so they can never be
exposed by these dependencies.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status

from app.auth.jwt import verify_token
from app.database.mongodb import get_database


_VALID_ROLES = frozenset({"admin", "hod", "faculty"})


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )


async def get_current_user(payload: dict = Depends(verify_token)) -> dict:
    """Resolve the authenticated user from the verified JWT payload.

    `verify_token` already raises 401 for missing/invalid/expired tokens.
    The token's subject is then resolved against the current database state so
    role/email changes (and deleted users) take effect immediately.
    """
    user_id = payload.get("sub")
    if not user_id:
        raise _unauthorized()

    try:
        user_oid = ObjectId(str(user_id))
    except (InvalidId, TypeError):
        raise _unauthorized()

    db = get_database()
    user = await db.users.find_one({"_id": user_oid})
    if user is None:
        raise _unauthorized()

    role = user.get("role")
    email = user.get("email")
    if role not in _VALID_ROLES or not email:
        raise _unauthorized()

    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "email": email,
        "role": role,
        "department": user.get("department"),
    }


def require_roles(*allowed_roles: str):
    """Dependency factory that allows only the given roles.

    Usage:
        @router.post("/", dependencies=[Depends(require_roles("admin", "hod"))])

    or to also receive the user object:
        async def handler(user=Depends(require_roles("admin"))): ...

    Returns 401 when unauthenticated (via `get_current_user`) and 403 when the
    caller is authenticated but their role is not permitted.
    """

    async def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return dependency
