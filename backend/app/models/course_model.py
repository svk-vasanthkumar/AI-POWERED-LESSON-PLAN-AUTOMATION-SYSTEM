from datetime import datetime, UTC

from bson import ObjectId


def create_course_document(
    course_code: str,
    course_name: str,
    department: str,
    semester: int,
    credits: int,
    faculty_ids: list[ObjectId],
    academic_year: str,
    short_form: str = None,
):
    return {
        "course_code": course_code.upper(),
        "course_name": course_name,
        "department": department,
        "semester": semester,
        "credits": credits,
        "faculty_ids": faculty_ids,
        "academic_year": academic_year,
        "short_form": short_form,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
