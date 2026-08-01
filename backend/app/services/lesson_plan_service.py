from app.database.mongodb import get_database
from app.models.lesson_plan_model import create_lesson_plan_document
from app.services.ai_service import generate_lesson_plan


async def generate_and_save_lesson_plan(syllabus_id: str):
    db = get_database()

    syllabus = await db.syllabi.find_one({"_id": __import__("bson").ObjectId(syllabus_id)})

    if syllabus is None:
        raise ValueError("Syllabus not found")

    lesson_plan = await generate_lesson_plan(
        syllabus["text"]
    )

    document = create_lesson_plan_document(
        filename=syllabus["filename"],
        filepath=syllabus["filepath"],
        extracted_text=syllabus["text"],
        lesson_plan=lesson_plan,
    )

    document["syllabus_id"] = syllabus["_id"]

    result = await db.lesson_plans.insert_one(document)

    return {
        "lesson_plan_id": str(result.inserted_id),
        "lesson_plan": lesson_plan,
    }