from app.database.mongodb import get_database
from app.models.lesson_plan_model import create_lesson_plan_document


async def save_lesson_plan(
    filename: str,
    filepath: str,
    extracted_text: str,
    lesson_plan: str,
):
    db = get_database()

    document = create_lesson_plan_document(
        filename,
        filepath,
        extracted_text,
        lesson_plan,
    )

    result = await db.lesson_plans.insert_one(document)

    return str(result.inserted_id)