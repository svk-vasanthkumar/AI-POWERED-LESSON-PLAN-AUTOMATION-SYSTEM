from datetime import datetime, UTC


def create_timetable_document(
    faculty_id: str,
    course_id: str,
    semester: int,
    schedule: list,
):
    return {
        "faculty_id": faculty_id,
        "course_id": course_id,
        "semester": semester,
        "schedule": schedule,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }