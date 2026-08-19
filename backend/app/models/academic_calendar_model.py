from datetime import datetime, UTC

from app.utils.calendar_dates import to_datetime, flatten_exam_range_dates


def _event_to_dict(event) -> dict:
    return {
        "type": event.type,
        "name": event.name,
        "date": to_datetime(event.date) if event.date else None,
        "start_date": (
            to_datetime(event.start_date)
            if event.start_date
            else None
        ),
        "end_date": (
            to_datetime(event.end_date)
            if event.end_date
            else None
        ),
    }


def _range_to_dict(rng) -> dict | None:
    if not rng:
        return None
    return {
        "start_date": to_datetime(rng.start_date),
        "end_date": to_datetime(rng.end_date),
        "name": rng.name,
    }


def create_calendar_document(data) -> dict:
    """
    Convert the validated AcademicCalendarCreate schema
    into the MongoDB academic-calendar document.
    """

    now = datetime.now(UTC)

    ranges_dict = {}
    for key in ("cia_1", "cia_2", "cia_3", "model_practical", "model_theory", "semester_end_practical", "semester_end_theory"):
        val = getattr(data, key, None)
        if val:
            ranges_dict[key] = {"start_date": val.start_date, "end_date": val.end_date}

    flattened = flatten_exam_range_dates(ranges_dict)
    combined_internal_exams = sorted(list(set((data.internal_exams or []) + flattened)))

    return {
        "academic_year": data.academic_year,
        "semester": data.semester,

        "semester_start": to_datetime(
            data.semester_start
        ),
        "semester_end": to_datetime(
            data.semester_end
        ),

        "working_days": data.working_days,

        "monthly_working_days": [
            {
                "month": item.month,
                "working_days": item.working_days,
            }
            for item in data.monthly_working_days
        ],

        "total_working_days": data.total_working_days,

        "holidays": [
            {
                "date": to_datetime(holiday.date),
                "name": holiday.name,
            }
            for holiday in data.holidays
        ],

        "events": [
            _event_to_dict(event)
            for event in data.events
        ],

        "special_days": [
            {
                "date": to_datetime(item.date),
                "timetable_day": item.timetable_day,
            }
            for item in data.special_days
        ],

        "cia_1": _range_to_dict(data.cia_1),
        "cia_2": _range_to_dict(data.cia_2),
        "cia_3": _range_to_dict(data.cia_3),
        "model_practical": _range_to_dict(data.model_practical),
        "model_theory": _range_to_dict(data.model_theory),
        "semester_end_practical": _range_to_dict(data.semester_end_practical),
        "semester_end_theory": _range_to_dict(data.semester_end_theory),
        "winter_vacation": _range_to_dict(data.winter_vacation),

        "internal_exams": combined_internal_exams,

        "raw_text": data.raw_text,

        "extraction_method": data.extraction_method,

        "original_filename": data.original_filename,

        "status": "pending_review",

        "created_at": now,
        "updated_at": now,
    }