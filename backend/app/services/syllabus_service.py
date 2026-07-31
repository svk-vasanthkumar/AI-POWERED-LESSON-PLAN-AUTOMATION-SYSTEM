from app.database.mongodb import get_database
from app.models.syllabus_model import create_syllabus_document


async def save_syllabus(
    filename: str,
    filepath: str,
    extracted_text: str,
):
    db = get_database()

    document = create_syllabus_document(
        filename,
        filepath,
        extracted_text,
    )

    result = await db.syllabi.insert_one(document)

    return str(result.inserted_id)