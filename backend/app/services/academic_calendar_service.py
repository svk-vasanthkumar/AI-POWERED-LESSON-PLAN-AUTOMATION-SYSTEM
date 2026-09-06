import asyncio
from datetime import UTC, datetime
from bson import ObjectId
from bson.errors import InvalidId

from pymongo.errors import DuplicateKeyError

from app.database.mongodb import get_database
from app.models.academic_calendar_model import create_calendar_document
from app.schemas.academic_calendar_schema import AcademicCalendarCreate
from app.services.academic_calendar_parser import parse_academic_calendar_text
from app.services.text_extraction_service import extract_text_with_method


async def create_calendar(
    data: AcademicCalendarCreate,
    status: str = "confirmed",
) -> str:
    db = get_database()

    existing = await db.academic_calendar.find_one(
        {
            "academic_year": data.academic_year,
            "semester": data.semester,
        }
    )

    if existing:
        raise ValueError("Calendar already exists")

    document = create_calendar_document(data)
    document["status"] = status

    try:
        result = await db.academic_calendar.insert_one(document)
    except DuplicateKeyError:
        raise ValueError("Calendar already exists")

    return str(result.inserted_id)



async def process_calendar_document(
    filepath: str,
    filename: str,
) -> dict:
    """Process an uploaded official academic-calendar document.

    Upload
        ↓
    Text extraction / OCR
        ↓
    Calendar parser
        ↓
    Structured calendar
        ↓
    Pending review
    """
    # OCR is CPU-heavy and synchronous. Run it outside the FastAPI event loop
    # so the API remains responsive while a scanned calendar is processed.
    extracted_text, extraction_method = await asyncio.to_thread(
        extract_text_with_method,
        filepath,
    )

    calendar = parse_academic_calendar_text(
        extracted_text,
        original_filename=filename,
        extraction_method=extraction_method,
    )

    return {
        "calendar": calendar,
        "raw_text": extracted_text,
        "extraction_method": extraction_method,
    }


async def create_pending_calendar(
    data: AcademicCalendarCreate,
) -> str:
    """Store an extracted calendar as pending_review.

    It is not the active/confirmed calendar yet.
    """
    db = get_database()

    document = create_calendar_document(data)
    document["status"] = "pending_review"

    result = await db.academic_calendar.insert_one(document)
    return str(result.inserted_id)


async def get_pending_calendar(
    calendar_id: str,
) -> dict | None:
    """Return a calendar waiting for Admin/HOD confirmation."""
    calendar = await get_calendar(calendar_id)

    if not calendar:
        return None

    if calendar.get("status") != "pending_review":
        return None

    return calendar


async def get_all_calendars() -> list[dict]:
    db = get_database()
    calendars = []

    async for document in db.academic_calendar.find().sort(
        [
            ("academic_year", -1),
            ("semester", 1),
        ]
    ):
        document["_id"] = str(document["_id"])
        calendars.append(document)

    return calendars


async def get_calendar(
    calendar_id: str,
) -> dict | None:
    db = get_database()

    try:
        object_id = ObjectId(calendar_id)
    except InvalidId:
        return None

    document = await db.academic_calendar.find_one({"_id": object_id})
    if document:
        document["_id"] = str(document["_id"])

    return document


async def confirm_calendar(
    calendar_id: str,
    data: AcademicCalendarCreate,
) -> bool:
    db = get_database()

    try:
        object_id = ObjectId(calendar_id)
    except InvalidId:
        return False

    existing = await db.academic_calendar.find_one({"_id": object_id})
    if existing is None:
        return False

    # Only one confirmed calendar may exist for a given academic year +
    # semester. Older confirmed versions are archived rather than deleted.
    await db.academic_calendar.update_many(
        {
            "academic_year": data.academic_year,
            "semester": data.semester,
            "status": "confirmed",
            "_id": {"$ne": object_id},
        },
        {"$set": {"status": "archived", "updated_at": datetime.now(UTC)}},
    )

    document = create_calendar_document(data)
    document["status"] = "confirmed"
    document["updated_at"] = datetime.now(UTC)
    document.pop("created_at", None)

    result = await db.academic_calendar.update_one(
        {"_id": object_id},
        {"$set": document},
    )

    return result.matched_count > 0


from app.models.academic_calendar_model import _event_to_dict, _range_to_dict, create_calendar_document
from app.schemas.academic_calendar_schema import AcademicCalendarCreate, AcademicCalendarUpdate
from app.utils.calendar_dates import to_datetime


async def update_calendar(
    calendar_id: str,
    data: AcademicCalendarCreate | AcademicCalendarUpdate,
) -> bool:
    db = get_database()

    try:
        object_id = ObjectId(calendar_id)
    except InvalidId:
        return False

    existing = await db.academic_calendar.find_one({"_id": object_id})
    if not existing:
        return False

    if isinstance(data, AcademicCalendarCreate):
        document = create_calendar_document(data)
        document["updated_at"] = datetime.now(UTC)
        document.pop("created_at", None)
        result = await db.academic_calendar.update_one(
            {"_id": object_id},
            {"$set": document},
        )
        return result.matched_count > 0

    updates: dict = {"updated_at": datetime.now(UTC)}
    dumped = data.model_dump(exclude_unset=True)

    if "semester_start" in dumped and data.semester_start:
        updates["semester_start"] = to_datetime(data.semester_start)
    if "semester_end" in dumped and data.semester_end:
        updates["semester_end"] = to_datetime(data.semester_end)
    if "working_days" in dumped and data.working_days is not None:
        updates["working_days"] = data.working_days
    if "monthly_working_days" in dumped and data.monthly_working_days is not None:
        updates["monthly_working_days"] = [
            {"month": item.month, "working_days": item.working_days}
            for item in data.monthly_working_days
        ]
    if "total_working_days" in dumped and data.total_working_days is not None:
        updates["total_working_days"] = data.total_working_days
    if "holidays" in dumped and data.holidays is not None:
        updates["holidays"] = [
            {"date": to_datetime(h.date), "name": h.name}
            for h in data.holidays
        ]
    if "events" in dumped and data.events is not None:
        updates["events"] = [_event_to_dict(e) for e in data.events]
    if "special_days" in dumped and data.special_days is not None:
        updates["special_days"] = [
            {"date": to_datetime(s.date), "timetable_day": s.timetable_day}
            for s in data.special_days
        ]

    for key in ("cia_1", "cia_2", "cia_3", "model_practical", "model_theory", "semester_end_practical", "semester_end_theory", "winter_vacation"):
        if key in dumped and getattr(data, key) is not None:
            updates[key] = _range_to_dict(getattr(data, key))

    if "internal_exams" in dumped and data.internal_exams is not None:
        updates["internal_exams"] = data.internal_exams

    result = await db.academic_calendar.update_one(
        {"_id": object_id},
        {"$set": updates},
    )

    return result.matched_count > 0


async def delete_calendar(
    calendar_id: str,
) -> bool:
    db = get_database()

    try:
        object_id = ObjectId(calendar_id)
    except InvalidId:
        return False

    result = await db.academic_calendar.delete_one({"_id": object_id})
    return result.deleted_count > 0