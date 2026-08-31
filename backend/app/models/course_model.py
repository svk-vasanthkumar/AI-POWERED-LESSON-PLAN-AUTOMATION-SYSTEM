from datetime import datetime, UTC

from bson import ObjectId


def create_course_document(
    course_code: str,
    course_name: str,
    department: str,
    semester: int,
    credits: int,
    faculty_id: ObjectId,
    academic_year: str,
):
    return {
        "course_code": course_code.upper(),
        "course_name": course_name,
        "department": department,
        "semester": semester,
        "credits": credits,
        "faculty_id": faculty_id,
        "academic_year": academic_year,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
