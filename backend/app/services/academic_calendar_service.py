import asyncio
from datetime import UTC, datetime
from bson import ObjectId
from bson.errors import InvalidId

from pymongo.errors import DuplicateKeyError

from app.database.mongodb import get_database
from app.models.academic_calendar_model import _event_to_dict, _range_to_dict, create_calendar_document
from app.schemas.academic_calendar_schema import AcademicCalendarCreate, AcademicCalendarUpdate
from app.services.academic_calendar_parser import parse_academic_calendar_text
from app.services.text_extraction_service import extract_text_with_method
from app.utils.calendar_dates import to_datetime


# The identity of an academic calendar is (academic_year, semester). This is
# enforced at the database level by the unique index ``uniq_calendar_year_semester``
# (see app/database/mongodb.py). These fields must stay in sync with that index.
_CALENDAR_IDENTITY_FIELDS = frozenset({"academic_year", "semester"})
_CALENDAR_IDENTITY_INDEX = "uniq_calendar_year_semester"


class CalendarAlreadyExistsError(Exception):
    """Raised when a calendar for the same academic_year + semester exists.

    This is a *domain* error, not a database error: it carries a clean,
    user-facing message and never exposes MongoDB collection names, index
    names, raw pymongo errors, or stack traces. The API layer maps it to a
    controlled ``409 Conflict`` response.
    """

    def __init__(self, academic_year: str, semester: int):
        self.academic_year = academic_year
        self.semester = semester
        super().__init__(
            f"Academic calendar for {academic_year} "
            f"Semester {semester} already exists."
        )


def _is_calendar_identity_conflict(exc: DuplicateKeyError) -> bool:
    """Return True only when ``exc`` is the academic_year/semester uniqueness
    conflict, and not some other duplicate-key violation.

    We deliberately do NOT treat every ``DuplicateKeyError`` as this conflict.
    A duplicate on any other index must keep propagating so it is never
    silently mislabelled as a calendar-identity conflict.
    """
    details = getattr(exc, "details", None) or {}

    # Preferred, most precise signal: the violated index' key pattern is exactly
    # (academic_year, semester).
    key_pattern = details.get("keyPattern")
    if isinstance(key_pattern, dict) and frozenset(key_pattern) == _CALENDAR_IDENTITY_FIELDS:
        return True

    # Fall back to the stable, explicit index name when available.
    message = str(exc)
    if _CALENDAR_IDENTITY_INDEX in message or _CALENDAR_IDENTITY_INDEX in str(details):
        return True

    return False


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

    A calendar is uniquely identified by (academic_year, semester). Uploading
    the same calendar twice must NOT crash with a raw database error. This is
    guarded on two levels:

      A. A fast pre-insert check that fails cleanly when a calendar for the same
         academic_year + semester already exists.
      B. A race-safe catch of the unique-index ``DuplicateKeyError`` for the
         case where two concurrent uploads both pass the check above and race to
         insert. The unique database constraint remains the FINAL protection;
         this only translates its error into a controlled domain error.

    Both raise :class:`CalendarAlreadyExistsError`, which the API maps to a
    409 response. No duplicate document is ever created.
    """
    db = get_database()

    # A. Existing calendar found before insert -> fail fast, cleanly.
    existing = await db.academic_calendar.find_one(
        {
            "academic_year": data.academic_year,
            "semester": data.semester,
        }
    )
    if existing is not None:
        raise CalendarAlreadyExistsError(data.academic_year, data.semester)

    document = create_calendar_document(data)
    document["status"] = "pending_review"

    # B. Concurrent-insert race: the pre-check can pass for two requests at once.
    #    The unique index is the last line of defence; map ONLY the
    #    academic_year/semester conflict to the domain error and let any other
    #    duplicate-key error propagate untouched.
    try:
        result = await db.academic_calendar.insert_one(document)
    except DuplicateKeyError as exc:
        if _is_calendar_identity_conflict(exc):
            raise CalendarAlreadyExistsError(
                data.academic_year,
                data.semester,
            ) from exc
        raise

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
) -> bool:
    db = get_database()

    try:
        object_id = ObjectId(calendar_id)
    except InvalidId:
        return False

    # Only an existing pending calendar can be confirmed.
    existing = await db.academic_calendar.find_one(
        {
            "_id": object_id,
            "status": "pending_review",
        }
    )

    if existing is None:
        return False

    academic_year = existing.get("academic_year")
    semester = existing.get("semester")

    # Archive any previously confirmed calendar for the same
    # academic year + semester.
    await db.academic_calendar.update_many(
        {
            "academic_year": academic_year,
            "semester": semester,
            "status": "confirmed",
            "_id": {"$ne": object_id},
        },
        {
            "$set": {
                "status": "archived",
                "updated_at": datetime.now(UTC),
            }
        },
    )

    # Confirm the SAME stored document.
    result = await db.academic_calendar.update_one(
        {
            "_id": object_id,
            "status": "pending_review",
        },
        {
            "$set": {
                "status": "confirmed",
                "updated_at": datetime.now(UTC),
            }
        },
    )

    return result.matched_count > 0


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