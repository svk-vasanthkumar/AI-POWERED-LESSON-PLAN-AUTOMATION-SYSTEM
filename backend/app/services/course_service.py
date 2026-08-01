from bson import ObjectId

from app.database.mongodb import get_database
from app.models.course_model import create_course_document


async def create_course(data):
    db = get_database()

    faculty = await db.faculty.find_one(
        {"_id": ObjectId(data.faculty_id)}
    )

    if faculty is None:
        raise ValueError("Faculty not found")

    existing = await db.courses.find_one(
        {"course_code": data.course_code.upper()}
    )

    if existing:
        raise ValueError("Course already exists")

    document = create_course_document(
        data.course_code,
        data.course_name,
        data.department,
        data.semester,
        data.credits,
        data.faculty_id,
    )

    result = await db.courses.insert_one(document)

    return str(result.inserted_id)