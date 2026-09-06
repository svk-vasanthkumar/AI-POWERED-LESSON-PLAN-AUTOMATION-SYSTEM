from datetime import UTC, datetime
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import get_database
from app.models.course_model import create_course_document
from app.utils.object_id import to_object_id
from app.services.notification_service import create_notification


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

    Stringifies ``_id`` and the ``faculty_id`` / ``faculty_ids`` references.
    Legacy string references pass through unchanged so old documents stay readable.
    """
    if doc is None:
        return doc
    doc = dict(doc)
    if isinstance(doc.get("_id"), ObjectId):
        doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("faculty_id"), ObjectId):
        doc["faculty_id"] = str(doc["faculty_id"])
    if "faculty_ids" in doc:
        doc["faculty_ids"] = [str(fid) if isinstance(fid, ObjectId) else fid for fid in doc["faculty_ids"]]
    return doc


async def create_course(data):
    db = get_database()

    if not data.faculty_ids:
        raise ValueError("At least one faculty member must be assigned")

    faculty_oids = [to_object_id(fid, field="faculty_ids") for fid in data.faculty_ids]
    
    faculties = await db.faculty.find({"_id": {"$in": faculty_oids}}).to_list(None)
    if len(faculties) != len(faculty_oids):
        raise ValueError("One or more faculty members not found")

    for faculty in faculties:
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
        department=data.department,
        semester=data.semester,
        credits=data.credits,
        faculty_ids=faculty_oids,
        academic_year=data.academic_year,
        short_form=data.short_form,
    )

    try:
        result = await db.courses.insert_one(document)
    except DuplicateKeyError:
        raise ValueError("Course already exists")

    # Fetch user_id for the faculties to send a notification
    for faculty in faculties:
        if "user_id" in faculty:
            await create_notification(
                user_id=str(faculty["user_id"]),
                title="New Course Assigned",
                message=f"You have been assigned to teach {data.course_name} ({data.course_code}).",
                type="info"
            )

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
    
    The ``faculty_id`` reference is validated (existence + ObjectId normalization)
    so the relationship stays consistent. Updates may change the ``course_code``
    provided it does not violate the (course_code, academic_year) unique constraint.
    """
    from pymongo.errors import DuplicateKeyError
    
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")

    existing = await db.courses.find_one({"_id": course_oid})
    if existing is None:
        return 0

    if not data.faculty_ids:
        raise ValueError("At least one faculty member must be assigned")

    faculty_oids = [to_object_id(fid, field="faculty_ids") for fid in data.faculty_ids]
    faculties = await db.faculty.find({"_id": {"$in": faculty_oids}}).to_list(None)
    if len(faculties) != len(faculty_oids):
        raise ValueError("One or more faculty members not found")

    for faculty in faculties:
        if faculty["department"].strip().lower() != data.department.strip().lower():
            raise ValueError("Course department must match faculty department")

    updates = {
        "course_code": data.course_code.upper(),
        "course_name": data.course_name,
        "department": data.department,
        "semester": data.semester,
        "credits": data.credits,
        "faculty_ids": faculty_oids,
        "academic_year": data.academic_year,
        "short_form": data.short_form,
        "updated_at": datetime.now(UTC),
    }

    try:
        result = await db.courses.update_one({"_id": course_oid}, {"$set": updates})
        return 1 if result.matched_count else 0
    except DuplicateKeyError:
        raise ValueError("Another course already uses this course code for the selected academic year")


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


async def clone_course(course_id: str, new_faculty_ids: list[str], new_academic_year: str) -> str:
    """Clone a course along with its associated syllabus and lesson plan."""
    db = get_database()
    course_oid = to_object_id(course_id, field="course_id")
    
    if not new_faculty_ids:
        raise ValueError("At least one faculty member must be assigned")

    faculty_oids = [to_object_id(fid, field="new_faculty_ids") for fid in new_faculty_ids]

    # 1. Clone Course
    course = await db.courses.find_one({"_id": course_oid})
    if not course:
        raise ValueError("Original course not found")
        
    faculties = await db.faculty.find({"_id": {"$in": faculty_oids}}).to_list(None)
    if len(faculties) != len(faculty_oids):
        raise ValueError("One or more new faculty not found")

    new_course = create_course_document(
        course_code=course["course_code"],
        course_name=course["course_name"],
        department=course["department"],
        semester=course["semester"],  # Keeps same semester
        credits=course["credits"],
        faculty_ids=faculty_oids,
        academic_year=new_academic_year,
    )
    result = await db.courses.insert_one(new_course)
    new_course_id = result.inserted_id

    # 2. Clone Syllabus (latest one)
    syllabus = await db.syllabi.find_one(
        {"course_id": course_oid}, sort=[("created_at", -1)]
    )
    new_syllabus_id = None
    if syllabus:
        from app.models.syllabus_model import create_syllabus_document
        new_syllabus = create_syllabus_document(
            course_id=new_course_id,
            filename=syllabus.get("filename"),
            filepath=syllabus.get("filepath"),
            extracted_text=syllabus.get("text"),
            original_filename=syllabus.get("original_filename"),
            extraction_method=syllabus.get("extraction_method", "text"),
        )
        s_result = await db.syllabi.insert_one(new_syllabus)
        new_syllabus_id = s_result.inserted_id

    if new_syllabus_id:
        lesson_plan = await db.lesson_plans.find_one(
            {"course_id": course_oid}, sort=[("created_at", -1)]
        )
        if lesson_plan:
            from app.models.lesson_plan_model import create_lesson_plan_document
            new_lp = create_lesson_plan_document(
                course_id=new_course_id,
                syllabus_id=new_syllabus_id,
                lesson_plan=lesson_plan.get("lesson_plan"),
                structured_plan=lesson_plan.get("structured_plan"),
            )
            await db.lesson_plans.insert_one(new_lp)
            
    for faculty in faculties:
        if "user_id" in faculty:
            await create_notification(
                user_id=str(faculty["user_id"]),
                title="Course Reassigned",
                message=f"You have been assigned to teach {course['course_name']} ({course['course_code']}) for the {new_academic_year} academic year.",
                type="info"
            )
            
    return str(new_course_id)