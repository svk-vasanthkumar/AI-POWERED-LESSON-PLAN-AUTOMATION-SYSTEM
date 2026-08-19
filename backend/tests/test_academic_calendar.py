"""Academic Calendar expansion tests (Task #3).

Covers the expanded calendar model/schema/service/API: semester bounds, CIA
I/II/III, model practical/theory, semester-end practical/theory, winter
vacation, holidays, special timetable-swap days, validation, duplicate
identity handling, legacy-document compatibility, and calendar CRUD.

These tests exercise the service layer directly against an in-memory
``mongomock_motor`` database, mirroring the existing test-suite style (see
``tests/test_database_integrity.py``).
"""

import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

import app.database.mongodb as mongodb
from app.schemas.academic_calendar_schema import (
    AcademicCalendarCreate,
    AcademicCalendarUpdate,
)
from app.services.academic_calendar_service import (
    create_calendar,
    delete_calendar,
    get_calendar,
    update_calendar,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    monkeypatch.setattr(mongodb, "database", database)
    return database


def _base_kwargs(academic_year="2026-2027", semester=1, **overrides):
    kwargs = dict(
        academic_year=academic_year,
        semester=semester,
        semester_start="2026-06-01",
        semester_end="2026-11-30",
        working_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    )
    kwargs.update(overrides)
    return kwargs


def _payload(**overrides):
    return AcademicCalendarCreate(**_base_kwargs(**overrides))


# --- Valid semester calendar -------------------------------------------------


def test_valid_semester_calendar_is_created(db):
    calendar_id = _run(create_calendar(_payload()))

    stored = _run(get_calendar(calendar_id))
    assert stored["academic_year"] == "2026-2027"
    assert stored["semester"] == 1
    assert stored["working_days"] == [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    ]


# --- Invalid semester range ---------------------------------------------------


def test_invalid_semester_range_is_rejected():
    with pytest.raises(ValidationError, match="semester_end must be on or after"):
        _payload(semester_start="2026-11-30", semester_end="2026-06-01")


# --- CIA I / II / III ranges ---------------------------------------------------


def test_valid_cia_1_range_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(
                cia_1={"start_date": "2026-07-10", "end_date": "2026-07-12"},
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["cia_1"]["name"] is None


def test_valid_cia_2_range_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(
                cia_2={"start_date": "2026-08-10", "end_date": "2026-08-12"},
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["cia_2"] is not None


def test_valid_cia_3_range_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(
                cia_3={"start_date": "2026-09-10", "end_date": "2026-09-12"},
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["cia_3"] is not None


# --- Model practical / theory ranges -------------------------------------------


def test_model_practical_range_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(
                model_practical={"start_date": "2026-10-01", "end_date": "2026-10-03"},
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["model_practical"] is not None


def test_model_theory_range_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(
                model_theory={"start_date": "2026-10-05", "end_date": "2026-10-07"},
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["model_theory"] is not None


# --- Semester-end practical / theory ranges ------------------------------------


def test_semester_end_practical_range_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(
                semester_end_practical={
                    "start_date": "2026-11-10",
                    "end_date": "2026-11-12",
                },
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["semester_end_practical"] is not None


def test_semester_end_theory_range_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(
                semester_end_theory={
                    "start_date": "2026-11-15",
                    "end_date": "2026-11-20",
                },
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["semester_end_theory"] is not None

    # Exam ranges flatten into the legacy internal_exams list so the existing
    # (unmodified) scheduler keeps blocking these days.
    assert "2026-11-15" in stored["internal_exams"]
    assert "2026-11-20" in stored["internal_exams"]


# --- Winter vacation ------------------------------------------------------------


def test_vacation_range_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(
                semester_start="2026-06-01",
                semester_end="2026-12-31",
                winter_vacation={"start_date": "2026-12-15", "end_date": "2026-12-31"},
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["winter_vacation"] is not None
    # Vacation is not an exam period, so it should NOT feed internal_exams.
    assert stored["internal_exams"] == []


# --- Holidays --------------------------------------------------------------------


def test_holiday_date_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(holidays=[{"date": "2026-08-15", "name": "Independence Day"}])
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert len(stored["holidays"]) == 1
    assert stored["holidays"][0]["name"] == "Independence Day"


def test_duplicate_holiday_dates_are_rejected():
    with pytest.raises(ValidationError, match="Duplicate holiday date"):
        _payload(
            holidays=[
                {"date": "2026-08-15", "name": "Independence Day"},
                {"date": "2026-08-15", "name": "Duplicate"},
            ]
        )


# --- Special timetable days ------------------------------------------------------


def test_special_timetable_day_is_stored(db):
    calendar_id = _run(
        create_calendar(
            _payload(
                special_days=[{"date": "2026-08-17", "timetable_day": "Thursday"}]
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["special_days"][0]["timetable_day"] == "Thursday"


def test_thursday_timetable_swap_example(db):
    # 17.08.2026 -> Thursday Timetable
    calendar_id = _run(
        create_calendar(
            _payload(
                special_days=[{"date": "2026-08-17", "timetable_day": "thu"}]
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["special_days"][0]["timetable_day"] == "Thursday"


def test_friday_timetable_swap_example(db):
    # 12.09.2026 -> Friday Timetable
    calendar_id = _run(
        create_calendar(
            _payload(
                special_days=[{"date": "2026-09-12", "timetable_day": "friday"}]
            )
        )
    )
    stored = _run(get_calendar(calendar_id))
    assert stored["special_days"][0]["timetable_day"] == "Friday"


def test_invalid_special_timetable_weekday_is_rejected():
    with pytest.raises(ValidationError, match="Invalid weekday"):
        _payload(special_days=[{"date": "2026-08-17", "timetable_day": "Blursday"}])


# --- Invalid dates ----------------------------------------------------------------


def test_invalid_date_is_rejected():
    with pytest.raises(ValidationError):
        _payload(semester_start="not-a-date")


def test_invalid_legacy_internal_exam_date_is_rejected():
    with pytest.raises(ValidationError, match="Invalid date"):
        _payload(internal_exams=["not-a-date"])


def test_range_outside_semester_bounds_is_rejected():
    with pytest.raises(ValidationError, match="must fall within the semester"):
        _payload(
            cia_1={"start_date": "2027-01-01", "end_date": "2027-01-03"},
        )


def test_invalid_working_day_is_rejected():
    with pytest.raises(ValidationError, match="Invalid weekday"):
        _payload(working_days=["Funday"])


# --- Duplicate academic_year + semester -------------------------------------------


def test_duplicate_academic_year_and_semester_is_rejected(db):
    _run(create_calendar(_payload(academic_year="2026-2027", semester=1)))

    with pytest.raises(ValueError, match="Calendar already exists"):
        _run(
            create_calendar(
                _payload(
                    academic_year="2026-2027",
                    semester=1,
                    cia_1={"start_date": "2026-07-01", "end_date": "2026-07-02"},
                )
            )
        )


def test_different_academic_year_is_allowed(db):
    _run(create_calendar(_payload(academic_year="2026-2027", semester=1)))
    _run(create_calendar(_payload(academic_year="2027-2028", semester=1)))

    assert _run(db.academic_calendar.count_documents({})) == 2


# --- Legacy compatibility ----------------------------------------------------------


def test_existing_legacy_calendar_document_remains_readable(db):
    # Simulate a pre-expansion calendar (Database Integrity Task #2 shape):
    # flat holidays/internal_exams lists, no structured ranges/special_days.
    result = _run(
        db.academic_calendar.insert_one(
            {
                "academic_year": "2023-2024",
                "semester": 1,
                "semester_start": "2023-06-01",
                "semester_end": "2023-11-30",
                "working_days": ["Monday", "Tuesday"],
                "holidays": ["2023-08-15"],
                "internal_exams": ["2023-09-01"],
            }
        )
    )

    stored = _run(get_calendar(str(result.inserted_id)))
    assert stored is not None
    assert stored["holidays"] == ["2023-08-15"]
    assert stored["internal_exams"] == ["2023-09-01"]


# --- Calendar CRUD ------------------------------------------------------------------


def test_calendar_get_update_delete_lifecycle(db):
    calendar_id = _run(create_calendar(_payload()))

    # GET
    fetched = _run(get_calendar(calendar_id))
    assert fetched is not None

    # UPDATE — add a holiday, leave everything else untouched.
    update_payload = AcademicCalendarUpdate(
        holidays=[{"date": "2026-08-15", "name": "Independence Day"}]
    )
    modified = _run(update_calendar(calendar_id, update_payload))
    assert modified == 1

    updated = _run(get_calendar(calendar_id))
    assert len(updated["holidays"]) == 1
    assert updated["academic_year"] == "2026-2027"  # identity untouched
    assert updated["working_days"] == [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    ]  # untouched by the update

    # DELETE
    deleted = _run(delete_calendar(calendar_id))
    assert deleted == 1

    gone = _run(get_calendar(calendar_id))
    assert gone is None


def test_update_nonexistent_calendar_returns_zero(db):
    from bson import ObjectId

    modified = _run(
        update_calendar(str(ObjectId()), AcademicCalendarUpdate(working_days=["Monday"]))
    )
    assert modified == 0


def test_delete_nonexistent_calendar_returns_zero(db):
    from bson import ObjectId

    deleted = _run(delete_calendar(str(ObjectId())))
    assert deleted == 0
