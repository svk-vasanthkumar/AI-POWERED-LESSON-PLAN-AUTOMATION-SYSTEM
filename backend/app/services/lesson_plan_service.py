from bson import ObjectId

from app.database.mongodb import get_database
from app.models.lesson_plan_model import create_lesson_plan_document
from app.services.ai_service import generate_lesson_plan, structured_to_topic_text
from app.utils.object_id import to_object_id


class LessonPlanInUseError(Exception):
    """Raised when a lesson plan cannot be deleted because records depend on it.

    The API layer maps this to a controlled 409 CONFLICT. Deleting the lesson
    plan would otherwise orphan the generated schedules that reference it via
    ``lesson_plan_id``, so restriction is preferred over a destructive cascade
    (the project has no deliberate cascade policy).
    """

    def __init__(self, dependencies: dict[str, int]):
        self.dependencies = dependencies
        summary = ", ".join(f"{count} {name}" for name, count in dependencies.items())
        super().__init__(
            "Lesson plan cannot be deleted while it is referenced by other "
            f"records ({summary}). Remove them first."
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


async def generate_and_save_lesson_plan(syllabus_id: str):
    db = get_database()

    # Validate & convert the incoming id via the shared helper so a malformed
    # id returns a clean 400 instead of an unhandled 500.
    syllabus_oid = to_object_id(syllabus_id, field="syllabus_id")

    syllabus = await db.syllabi.find_one({"_id": syllabus_oid})

    if syllabus is None:
        raise ValueError("Syllabus not found")

    # The AI service now returns a validated, structured LessonPlanAIOutput.
    structured = await generate_lesson_plan(syllabus["text"])

    # Flatten the structured plan into an ordered, newline-delimited topic
    # string so existing consumers (e.g. the scheduler, which splits
    # ``lesson_plan`` on newlines) keep working unchanged.
    lesson_plan_text = structured_to_topic_text(structured)

    # JSON-safe dict for MongoDB storage and API responses.
    structured_dict = structured.model_dump(mode="json")

    # Inherit the course relationship from the parent syllabus. Normalize
    # through the helper so it is stored as an ObjectId even if the parent
    # syllabus stored course_id as a legacy string.
    raw_course_id = syllabus.get("course_id")
    if not raw_course_id:
        # Fallback for old documents that lack course_id
        raw_course_id = str(ObjectId())
        
    course_id = to_object_id(raw_course_id, field="course_id")

    document = create_lesson_plan_document(
        course_id=course_id,
        syllabus_id=syllabus["_id"],
        lesson_plan=lesson_plan_text,
        structured_plan=structured_dict,
    )

    result = await db.lesson_plans.insert_one(document)

    return {
        "lesson_plan_id": str(result.inserted_id),
        "course_id": str(course_id),
        "syllabus_id": str(syllabus["_id"]),
        "lesson_plan": lesson_plan_text,
        "structured_plan": structured_dict,
    }


async def delete_lesson_plan(lesson_id: str) -> int:
    """Deletes the lesson plan and cascades deletion to any generated schedules that 
    reference it (hassle-free deletion). Returns the deleted count (0 -> 404) 
    otherwise. A malformed id raises via ``to_object_id`` (-> 400).
    """
    db = get_database()
    lesson_oid = to_object_id(lesson_id, field="lesson_id")

    existing = await db.lesson_plans.find_one({"_id": lesson_oid})
    if existing is None:
        return 0

    dependent_schedules = await db.generated_schedules.count_documents(
        {"lesson_plan_id": {"$in": _id_variants(lesson_oid)}}
    )
    if dependent_schedules:
        # Cascade deletion: automatically remove any generated schedules referencing this lesson plan
        await db.generated_schedules.delete_many(
            {"lesson_plan_id": {"$in": _id_variants(lesson_oid)}}
        )

    result = await db.lesson_plans.delete_one({"_id": lesson_oid})
    return result.deleted_count
