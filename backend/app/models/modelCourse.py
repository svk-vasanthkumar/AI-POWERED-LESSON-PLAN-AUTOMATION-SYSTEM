from datetime import datetime, timezone

from bson import ObjectId


def create_course_document(
    course_code: str,
    course_name: str,
    department: str,
    semester: int,
    credits: int,
    faculty_id: str,
):
    return {
        "_id": ObjectId(),
        "course_code": course_code.strip().upper(),
        "course_name": course_name.strip(),
        "department": department.strip(),
        "semester": semester,
        "credits": credits,
        "faculty_id": ObjectId(faculty_id),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }