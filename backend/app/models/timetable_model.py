from datetime import datetime, UTC


def create_timetable_document(
    faculty_id: str,
    course_id: str,
    semester: int,
    schedule: list,
    status: str = "VERIFIED",
    raw_text: str = None,
    original_filename: str = None,
    stored_filename: str = None,
    extraction_method: str = None,
):
    return {
        "faculty_id": faculty_id,
        "course_id": course_id,
        "semester": semester,
        "schedule": schedule,
        "status": status,
        "raw_text": raw_text,
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "extraction_method": extraction_method,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }