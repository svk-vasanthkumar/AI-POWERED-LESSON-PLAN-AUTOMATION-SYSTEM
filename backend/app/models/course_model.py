from datetime import datetime, UTC


def create_course_document(
    course_code: str,
    course_name: str,
    department: str,
    semester: int,
    credits: int,
    faculty_id: str,
):
    return {
        "course_code": course_code.upper(),
        "course_name": course_name,
        "department": department,
        "semester": semester,
        "credits": credits,
        "faculty_id": faculty_id,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }