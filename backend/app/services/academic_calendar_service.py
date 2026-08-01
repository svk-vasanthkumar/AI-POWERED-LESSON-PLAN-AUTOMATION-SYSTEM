from app.database.mongodb import get_database
from app.models.academic_calendar_model import create_calendar_document


async def create_calendar(data):
    db = get_database()

    existing = await db.academic_calendar.find_one(
        {
            "academic_year": data.academic_year,
            "semester": data.semester,
        }
    )

    if existing:
        raise ValueError(
            "Calendar already exists"
        )

    document = create_calendar_document(
        data.academic_year,
        data.semester,
        data.semester_start,
        data.semester_end,
        data.working_days,
        data.holidays,
        data.internal_exams,
    )

    result = await db.academic_calendar.insert_one(
        document
    )

    return str(result.inserted_id)