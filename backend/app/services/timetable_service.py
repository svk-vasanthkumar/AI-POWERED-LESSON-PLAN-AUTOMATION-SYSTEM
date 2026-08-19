"""Timetable persistence + business rules.

Handles period-aware timetable documents (see
``app.schemas.timetable_schema`` / ``app.utils.timetable_periods``) while
keeping legacy clock-time documents readable and untouched.

Scheduler allocation is intentionally NOT modified here — this only makes the
timetable data model/API ready for the next scheduler task (Task #5).
"""

from datetime import datetime, UTC

from bson import ObjectId
from bson.errors import InvalidId

from app.database.mongodb import get_database
from app.models.timetable_model import create_timetable_document
from app.utils.object_id import to_object_id
from app.utils.timetable_periods import periods_overlap


class TimetableInUseError(Exception):
    """Raised when a timetable cannot be deleted because records depend on it.

    The API layer maps this to a controlled 409 CONFLICT. Deleting the
    timetable would otherwise orphan the generated schedules that reference it
    via ``timetable_id``, so restriction is preferred over a destructive
    cascade (the project has no deliberate cascade policy).
    """

    def __init__(self, dependencies: dict[str, int]):
        self.dependencies = dependencies
        summary = ", ".join(f"{count} {name}" for name, count in dependencies.items())
        super().__init__(
            "Timetable cannot be deleted while it is referenced by other records "
            f"({summary}). Remove them first."
        )


# Collections that hold a ``timetable_id`` reference back to a timetable. Used
# to protect against orphaning dependent records on delete.
_TIMETABLE_DEPENDENTS = (
    ("generated_schedules", "generated schedule(s)"),
)


def _id_variants(value) -> list:
    """Both ObjectId and string forms of an id (legacy-compatible queries)."""
    variants = [value, str(value)]
    if not isinstance(value, ObjectId):
        try:
            variants.append(ObjectId(str(value)))
        except Exception:
            pass
    seen: set = set()
    unique: list = []
    for item in variants:
        key = (type(item).__name__, str(item))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


async def _count_timetable_dependencies(db, timetable_oid) -> dict[str, int]:
    """Count records that reference this timetable, keyed by a friendly name."""
    variants = _id_variants(timetable_oid)
    dependencies: dict[str, int] = {}
    for collection_name, label in _TIMETABLE_DEPENDENTS:
        count = await db[collection_name].count_documents(
            {"timetable_id": {"$in": variants}}
        )
        if count:
            dependencies[label] = count
    return dependencies


# --- helpers ---------------------------------------------------------------


def _serialize(doc: dict) -> dict:
    """Make a timetable document JSON-serializable.

    Stringifies ``_id`` and the ``faculty_id``/``course_id`` references when
    they are stored as native ``ObjectId`` (new records). Legacy string
    references are passed through unchanged so old documents stay readable.
    """
    if doc is None:
        return doc
    doc = dict(doc)
    if isinstance(doc.get("_id"), ObjectId):
        doc["_id"] = str(doc["_id"])
    for key in ("faculty_id", "course_id"):
        if isinstance(doc.get(key), ObjectId):
            doc[key] = str(doc[key])
    return doc


def _period_slots_by_day(schedule) -> dict[str, list[tuple[int, int]]]:
    """Group period-based slots by weekday as ``{day: [(start, end), ...]}``.

    Legacy clock-only slots (no period fields) are skipped — period overlap
    checks only apply between period-based slots.
    """
    slots: dict[str, list[tuple[int, int]]] = {}
    for item in schedule or []:
        start = item.get("period_start")
        end = item.get("period_end")
        if start is None or end is None:
            continue
        slots.setdefault(item.get("day"), []).append((start, end))
    return slots


async def _check_faculty_period_overlap(
    db, faculty_oid, schedule, exclude_id: ObjectId | None = None
):
    """Reject a schedule that clashes with the SAME faculty's other timetables.

    Compares period-based slots on the same weekday across every other
    timetable owned by ``faculty_oid``. Legacy clock-only slots are ignored
    (they carry no period numbers). Raises ``ValueError`` on the first clash.
    """
    new_slots = _period_slots_by_day([item.model_dump() for item in schedule])
    if not new_slots:
        return

    query = {"faculty_id": faculty_oid}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}

    async for existing in db.timetables.find(query):
        existing_slots = _period_slots_by_day(existing.get("schedule", []))
        for day, pairs in new_slots.items():
            for new_start, new_end in pairs:
                for ex_start, ex_end in existing_slots.get(day, []):
                    if periods_overlap(new_start, new_end, ex_start, ex_end):
                        raise ValueError(
                            f"Faculty already has a timetable slot on {day} "
                            f"Hour {ex_start}-{ex_end} that overlaps "
                            f"Hour {new_start}-{new_end}"
                        )


async def _validate_relationships(db, faculty_oid, course_oid, semester):
    """Validate faculty/course exist and (where present) the semester matches.

    Preserves the existing faculty_id/course_id/semester relationship without
    introducing a separate course entity.
    """
    faculty = await db.faculty.find_one({"_id": faculty_oid})
    if faculty is None:
        raise ValueError("Faculty not found")

    course = await db.courses.find_one({"_id": course_oid})
    if course is None:
        raise ValueError("Course not found")

    if (
        semester is not None
        and course.get("semester") is not None
        and course["semester"] != semester
    ):
        raise ValueError(
            f"Semester mismatch: course belongs to semester "
            f"{course['semester']}, not {semester}"
        )


# --- CRUD -------------------------------------------------------------------


async def create_timetable(data):
    db = get_database()

    # Validate & convert ids up front so malformed ids return 400 (via the
    # shared helper) instead of raising an unhandled 500.
    faculty_oid = to_object_id(data.faculty_id, field="faculty_id")
    course_oid = to_object_id(data.course_id, field="course_id")

    await _validate_relationships(db, faculty_oid, course_oid, data.semester)

    # No two period-based slots for the same faculty/day may overlap across
    # their existing timetables (within-timetable overlaps are already rejected
    # by the schema validator).
    await _check_faculty_period_overlap(db, faculty_oid, data.schedule)

    # Store the relationship keys as ObjectIds for NEW timetable documents.
    document = create_timetable_document(
        faculty_oid,
        course_oid,
        data.semester,
        [item.model_dump() for item in data.schedule],
    )

    result = await db.timetables.insert_one(document)

    return str(result.inserted_id)


async def get_all_timetables():
    db = get_database()
    timetables = []
    async for doc in db.timetables.find():
        timetables.append(_serialize(doc))
    return timetables


async def get_timetable(timetable_id: str):
    db = get_database()

    try:
        obj_id = ObjectId(timetable_id)
    except InvalidId:
        return None

    doc = await db.timetables.find_one({"_id": obj_id})
    if doc is None:
        return None
    return _serialize(doc)


async def update_timetable(timetable_id: str, data):
    """Apply a partial update. When ``schedule`` is supplied it fully replaces
    the stored schedule and is re-validated for faculty overlap (excluding this
    same document).
    """
    db = get_database()

    try:
        obj_id = ObjectId(timetable_id)
    except InvalidId:
        return 0

    existing = await db.timetables.find_one({"_id": obj_id})
    if existing is None:
        return 0

    updates: dict = {}

    # Resolve the effective faculty/course/semester after this update so
    # relationship + overlap checks run against the merged state.
    effective_faculty = existing.get("faculty_id")
    if data.faculty_id is not None:
        effective_faculty = to_object_id(data.faculty_id, field="faculty_id")
        updates["faculty_id"] = effective_faculty

    effective_course = existing.get("course_id")
    if data.course_id is not None:
        effective_course = to_object_id(data.course_id, field="course_id")
        updates["course_id"] = effective_course

    effective_semester = (
        data.semester if data.semester is not None else existing.get("semester")
    )
    if data.semester is not None:
        updates["semester"] = data.semester

    # Re-validate relationships whenever an identity field or the schedule
    # changes (so semester consistency stays enforced).
    if (
        data.faculty_id is not None
        or data.course_id is not None
        or data.semester is not None
    ) and isinstance(effective_faculty, ObjectId) and isinstance(
        effective_course, ObjectId
    ):
        await _validate_relationships(
            db, effective_faculty, effective_course, effective_semester
        )

    if data.schedule is not None:
        if isinstance(effective_faculty, ObjectId):
            await _check_faculty_period_overlap(
                db, effective_faculty, data.schedule, exclude_id=obj_id
            )
        updates["schedule"] = [item.model_dump() for item in data.schedule]

    if not updates:
        return 0

    updates["updated_at"] = datetime.now(UTC)

    result = await db.timetables.update_one({"_id": obj_id}, {"$set": updates})
    return result.modified_count


async def delete_timetable(timetable_id: str):
    """Delete a timetable, refusing to orphan dependent records.

    Raises :class:`TimetableInUseError` (-> 409) when any generated schedule
    still references the timetable. Returns the deleted count (0 -> 404)
    otherwise.
    """
    db = get_database()

    try:
        obj_id = ObjectId(timetable_id)
    except InvalidId:
        return 0

    existing = await db.timetables.find_one({"_id": obj_id})
    if existing is None:
        return 0

    dependencies = await _count_timetable_dependencies(db, obj_id)
    if dependencies:
        raise TimetableInUseError(dependencies)

    result = await db.timetables.delete_one({"_id": obj_id})
    return result.deleted_count
