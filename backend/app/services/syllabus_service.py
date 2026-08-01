from app.database.mongodb import get_database
from app.models.syllabus_model import create_syllabus_document


async def save_syllabus(
    course_id: str,
    filename: str,
    filepath: str,
    extracted_text: str,
) -> str:
    db = get_database()

    document = create_syllabus_document(
        course_id=course_id,
        filename=filename,
        filepath=filepath,
        extracted_text=extracted_text,
    )

    result = await db.syllabi.insert_one(document)

    return str(result.inserted_id)