from bson import ObjectId

from app.database.mongodb import get_database
from app.models.timetable_model import create_timetable_document


async def create_timetable(data):
    db = get_database()

    faculty = await db.faculty.find_one(
        {"_id": ObjectId(data.faculty_id)}
    )

    if faculty is None:
        raise ValueError("Faculty not found")

    course = await db.courses.find_one(
        {"_id": ObjectId(data.course_id)}
    )

    if course is None:
        raise ValueError("Course not found")

    document = create_timetable_document(
        data.faculty_id,
        data.course_id,
        data.semester,
        [item.model_dump() for item in data.schedule],
    )

    result = await db.timetables.insert_one(
        document
    )

    return str(result.inserted_id)