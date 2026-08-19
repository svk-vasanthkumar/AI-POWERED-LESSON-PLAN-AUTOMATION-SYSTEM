"""Reusable resource-level authorization helpers (Task #8).

These build on the EXISTING RBAC primitives and ownership model — they do not
introduce a new permission framework:

  * Role gating stays with ``get_current_user`` / ``require_roles`` in
    ``app.auth.dependencies`` (management writes remain admin/hod only there).
  * The faculty-ownership link reuses the Task #6 behaviour: an authenticated
    ``users`` record is matched to a ``faculty`` record by shared email — the
    ``users`` and ``faculty`` collections are separate and joined only by email
    (see ``app.services.progress_service._ensure_can_edit``).

Ownership of a resource is then decided through the NORMALIZED ObjectId
relationship introduced in Task #2 (``courses.faculty_id`` -> ``faculty._id``,
``timetables.faculty_id`` -> ``faculty._id``, ``syllabi.course_id`` /
``lesson_plans.course_id`` -> ``courses._id``) rather than an email-on-the
resource check. Legacy string references are still honoured because ids are
compared in string form, so old data keeps working without a migration.
"""

from __future__ import annotations

from bson import ObjectId
from fastapi import HTTPException, status

# Roles allowed to manage (create/update/delete) shared academic resources.
MANAGER_ROLES = ("admin", "hod")


def is_manager(user: dict | None) -> bool:
    """True for admin/hod — full management access (Part 7)."""
    return (user or {}).get("role") in MANAGER_ROLES


def ids_match(a, b) -> bool:
    """Compare two id references for equality.

    Handles the historical ObjectId/string inconsistency (Task #2): an
    ``ObjectId`` and its string form are treated as equal. ``None`` never
    matches anything.
    """
    if a is None or b is None:
        return False
    return str(a) == str(b)


def _id_variants(value) -> list:
    """Return both the ObjectId and string forms of an id for ``$in`` queries.

    Different collections stored relationship keys as either ObjectIds (newer
    writes) or strings (legacy). Querying with both forms keeps ownership
    lookups robust without migrating any data.
    """
    if value is None:
        return []
    variants = [value, str(value)]
    if not isinstance(value, ObjectId):
        try:
            variants.append(ObjectId(str(value)))
        except Exception:
            pass
    # De-duplicate while preserving order.
    seen: set = set()
    unique: list = []
    for item in variants:
        key = (type(item).__name__, str(item))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


async def resolve_faculty_for_user(db, user: dict | None) -> dict | None:
    """Resolve the ``faculty`` document linked to an authenticated user.

    The link is the shared email (the existing Task #6 ownership link). Returns
    ``None`` when the user has no email or no matching faculty record — callers
    must treat that as "ownership cannot be established".
    """
    email = (user or {}).get("email")
    if not email:
        return None
    return await db.faculty.find_one({"email": email.strip().lower()})


async def faculty_object_id_for_user(db, user: dict | None):
    """Return the ``faculty._id`` for the authenticated user, or ``None``."""
    faculty = await resolve_faculty_for_user(db, user)
    if faculty is None:
        return None
    return faculty.get("_id")


async def accessible_course_ids(db, user: dict | None) -> list | None:
    """Course ids the user may access.

    * Managers (admin/hod) -> ``None``, meaning "all courses" (no restriction).
    * Faculty -> the list of ``courses._id`` whose ``faculty_id`` matches their
      linked faculty record (via the Task #2 ObjectId relationship). An empty
      list when they own nothing / cannot be linked.
    * Any other role -> empty list.
    """
    if is_manager(user):
        return None

    if (user or {}).get("role") != "faculty":
        return []

    faculty_oid = await faculty_object_id_for_user(db, user)
    if faculty_oid is None:
        return []

    course_ids: list = []
    async for course in db.courses.find(
        {"faculty_id": {"$in": _id_variants(faculty_oid)}},
        {"_id": 1},
    ):
        course_ids.append(course["_id"])
    return course_ids


async def user_owns_faculty(db, user: dict | None, faculty_id) -> bool:
    """True when ``faculty_id`` references the user's own faculty record."""
    faculty_oid = await faculty_object_id_for_user(db, user)
    if faculty_oid is None:
        return False
    return ids_match(faculty_id, faculty_oid)


async def user_can_access_course(db, user: dict | None, course: dict | None) -> bool:
    """Decide whether a user may READ/access a specific course document."""
    if is_manager(user):
        return True
    if course is None:
        return False
    if (user or {}).get("role") != "faculty":
        return False
    return await user_owns_faculty(db, user, course.get("faculty_id"))


async def ensure_course_access(db, user: dict | None, course: dict | None) -> None:
    """Raise 403 unless the user may access ``course`` (404 handled by caller)."""
    if not await user_can_access_course(db, user, course):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource",
        )


async def ensure_course_id_access(db, user: dict | None, course_id) -> dict:
    """Load a course by id and enforce access, returning the course document.

    Raises 404 when the course does not exist and 403 when the caller may not
    access it. ``course_id`` is expected to already be a valid ObjectId (the
    caller validates it via ``to_object_id``).
    """
    course = await db.courses.find_one({"_id": {"$in": _id_variants(course_id)}})
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    await ensure_course_access(db, user, course)
    return course
