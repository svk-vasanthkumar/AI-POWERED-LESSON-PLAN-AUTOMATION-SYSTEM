from datetime import datetime, UTC


def create_calendar_document(
    academic_year: str,
    semester: int,
    semester_start: str,
    semester_end: str,
    working_days: list,
    holidays: list,
    internal_exams: list,
):
    return {
        "academic_year": academic_year,
        "semester": semester,
        "semester_start": semester_start,
        "semester_end": semester_end,
        "working_days": working_days,
        "holidays": holidays,
        "internal_exams": internal_exams,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }