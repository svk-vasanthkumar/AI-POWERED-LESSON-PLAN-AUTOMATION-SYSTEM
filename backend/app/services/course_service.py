from datetime import UTC, datetime
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import get_database
from app.models.course_model import create_course_document
from app.utils.object_id import to_object_id


class CourseInUseError(Exception):
    """Raised when a course cannot be deleted because other records depend on it.

    The API layer maps this to a controlled 409 CONFLICT. Deleting the course
    would otherwise orphan the referenced timetables / syllabi / lesson plans /
    generated schedules, so restriction is preferred over a destructive cascade
    (the project has no deliberate cascade policy).
    """

    def __init__(self, dependencies: dict[str, int]):
        self.dependencies = dependencies
        summary = ", ".join(f"{count} {name}" for name, count in dependencies.items())
        super().__init__(
            "Course cannot be deleted while it is referenced by other records "
            f"({summary}). Remove or reassign them first."
        )


# Collections that hold a ``course_id`` reference back to a course. Used to
# protect against orphaning dependent records on delete.
_COURSE_DEPENDENTS = (
    ("timetables", "timetable(s)"),
    ("syllabi", "syllabus/syllabi"),
    ("lesson_plans", "lesson plan(s)"),
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


def _serialize(doc: dict) -> dict:
    """Make a course document JSON-serializable.

    Stringifies ``_id`` and the ``faculty_id`` reference when stored as a native
    ObjectId (new records). Legacy string references pass through unchanged so
    old documents stay readable.
    """
    if doc is None:
        return doc
    doc = dict(doc)
    if isinstance(doc.get("_id"), ObjectId):
        doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("faculty_id"), ObjectId):
        doc["faculty_id"] = str(doc["faculty_id"])
    return doc


async def create_course(data):
    db = get_database()

    # Validate & convert the faculty reference via the shared helper
    faculty_oid = to_object_id(data.faculty_id, field="faculty_id")

    # Ensure faculty profile exists
    faculty = await db.faculty.find_one({"_id": faculty_oid})

    if not faculty:
        raise ValueError("Faculty not found")

    # Validate department match between course and faculty
    if faculty["department"].strip().lower() != data.department.strip().lower():
        raise ValueError("Course department must match faculty department")

    # Prevent duplicate course code
    existing_course = await db.courses.find_one(
        {"course_code": data.course_code.strip().upper()}
    )

    if existing_course:
        raise ValueError("Course already exists")

    document = create_course_document(
        data.course_code,
        data.course_name,
        data.department,
        data.semester,
        data.credits,
        faculty["_id"],
    )

    try:
        result = await db.courses.insert_one(document)
    except DuplicateKeyError:
        raise ValueError("Course already exists")

    return str(result.inserted_id)


async def get_all_courses(course_ids: list | None = None):
    """List courses, optionally restricted to a set of course ObjectIds.

    ``course_ids=None`` returns every course (admin/hod). A list restricts the
    result to those ids (faculty read-scoping). An empty list returns nothing.
    """
    db = get_database()

    query: dict = {}
    if course_ids is not None:
        if not course_ids:
            return []
        query = {"_id": {"$in": list(course_ids)}}

    courses = []
    async for doc in db.courses.find(query):
        courses.append(_serialize(doc))
    return courses


async def get_course(course_id: str):
    """Return a single serialized course, or ``None`` when not found.

    ``course_id`` is validated via the shared helper (-> 400 for malformed ids).
    """
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    course = await db.courses.find_one({"_id": course_oid})
    return _serialize(course) if course else None


async def update_course(course_id: str, data):
    """Apply an update to a course.

    ``course_code`` is intentionally NOT part of ``CourseUpdate`` so the unique
    index on ``courses.course_code`` can never be bypassed by an update. The
    ``faculty_id`` reference is validated (existence + ObjectId normalization)
    so the relationship stays consistent.
    """
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    existing = await db.courses.find_one({"_id": course_oid})
    if existing is None:
        return 0

    faculty_oid = to_object_id(data.faculty_id, field="faculty_id")
    faculty = await db.faculty.find_one({"_id": faculty_oid})
    if not faculty:
        raise ValueError("Faculty not found")

    if faculty["department"].strip().lower() != data.department.strip().lower():
        raise ValueError("Course department must match faculty department")

    updates = {
        "course_name": data.course_name,
        "department": data.department,
        "semester": data.semester,
        "credits": data.credits,
        "faculty_id": faculty["_id"],
        "updated_at": datetime.now(UTC),
    }

    result = await db.courses.update_one({"_id": course_oid}, {"$set": updates})
    return 1 if result.matched_count else 0


async def _count_course_dependencies(db, course_oid) -> dict[str, int]:
    """Count records that reference this course, keyed by a friendly name."""
    variants = _id_variants(course_oid)
    dependencies: dict[str, int] = {}
    for collection_name, label in _COURSE_DEPENDENTS:
        count = await db[collection_name].count_documents(
            {"course_id": {"$in": variants}}
        )
        if count:
            dependencies[label] = count
    return dependencies


async def delete_course(course_id: str) -> int:
    """Delete a course, refusing to orphan dependent records.

    Raises :class:`CourseInUseError` (-> 409) when any timetable, syllabus,
    lesson plan or generated schedule still references the course. Returns the
    deleted count (0 -> 404) otherwise.
    """
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    existing = await db.courses.find_one({"_id": course_oid})
    if existing is None:
        return 0

    dependencies = await _count_course_dependencies(db, course_oid)
    if dependencies:
        raise CourseInUseError(dependencies)

    result = await db.courses.delete_one({"_id": course_oid})
    return result.deleted_count