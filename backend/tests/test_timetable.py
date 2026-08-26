"""Faculty Timetable expansion tests (Task #4).

Covers the period-aware timetable model/schema/service/API: single periods,
multi-period & lab blocks, period-number/range validation, the lunch guarantee,
faculty/course relationship + semester consistency, cross-faculty and
within-timetable overlap rejection, Monday-Saturday support, backward
compatibility with legacy clock-time documents, CRUD, and special
timetable-day compatibility.

These tests exercise the service/schema layers directly against an in-memory
``mongomock_motor`` database, mirroring the existing test-suite style (see
``tests/test_academic_calendar.py`` / ``tests/test_database_integrity.py``).
"""

import asyncio

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

import app.database.mongodb as mongodb
from app.schemas.timetable_schema import TimetableCreate, TimetableUpdate
from app.services.timetable_service import (
    create_timetable,
    delete_timetable,
    get_all_timetables,
    get_timetable,
    update_timetable,
)
from app.utils.timetable_periods import (
    LUNCH_AFTER_PERIOD,
    TEACHING_PERIODS,
    describe_period_structure,
    entries_for_timetable_day,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    monkeypatch.setattr(mongodb, "database", database)
    return database


# --- helpers ---------------------------------------------------------------


async def _seed(db, semester=1, faculty_id="FAC001", course_code="CS101"):
    """Insert a faculty + course directly and return their ObjectIds."""
    fac = await db.faculty.insert_one(
        {
            "faculty_id": faculty_id,
            "name": "Seed Faculty",
            "email": f"{faculty_id}@example.com",
            "department": "CSE",
            "designation": "Professor",
        }
    )
    crs = await db.courses.insert_one(
        {
            "course_code": course_code,
            "course_name": "Intro to CS",
            "department": "CSE",
            "semester": semester,
            "credits": 4,
            "faculty_id": fac.inserted_id,
        }
    )
    return fac.inserted_id, crs.inserted_id


def _payload(faculty_oid, course_oid, schedule, semester=1):
    return TimetableCreate(
        faculty_id=str(faculty_oid),
        course_id=str(course_oid),
        semester=semester,
        schedule=schedule,
    )


# --- 1. Valid single period --------------------------------------------------


def test_valid_single_period(db):
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(
                fac,
                crs,
                [{"day": "Monday", "period_start": 2, "period_end": 2}],
            )
        )
    )
    stored = _run(get_timetable(timetable_id))
    slot = stored["schedule"][0]
    assert slot["period_start"] == 2 and slot["period_end"] == 2


# --- 2. Valid multi-period block --------------------------------------------


def test_valid_multi_period_block(db):
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(
                fac,
                crs,
                [{"day": "Tuesday", "period_start": 1, "period_end": 3}],
            )
        )
    )
    stored = _run(get_timetable(timetable_id))
    slot = stored["schedule"][0]
    assert (slot["period_start"], slot["period_end"]) == (1, 3)


# --- 3. Valid lab block (spans the lunch break) ------------------------------


def test_valid_lab_block(db):
    fac, crs = _run(_seed(db))
    # Hour 5-7 lab.
    timetable_id = _run(
        create_timetable(
            _payload(
                fac,
                crs,
                [
                    {
                        "day": "Monday",
                        "period_start": 5,
                        "period_end": 7,
                        "subject": "DBMS Lab",
                    }
                ],
            )
        )
    )
    stored = _run(get_timetable(timetable_id))
    slot = stored["schedule"][0]
    assert (slot["period_start"], slot["period_end"]) == (5, 7)
    assert slot["subject"] == "DBMS Lab"


def test_block_may_span_lunch(db):
    # Hour 3-5 covers Hours 3, 4, 5 (lunch between 4 and 5 is simply skipped).
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(
                fac,
                crs,
                [{"day": "Wednesday", "period_start": 3, "period_end": 5}],
            )
        )
    )
    stored = _run(get_timetable(timetable_id))
    assert stored["schedule"][0]["period_end"] == 5


# --- 4. Invalid period number ------------------------------------------------


def test_invalid_period_number_is_rejected():
    with pytest.raises(ValidationError, match="out of range"):
        ScheduleFactory(period_start=8, period_end=8)


def test_period_zero_is_rejected():
    with pytest.raises(ValidationError, match="out of range"):
        ScheduleFactory(period_start=0, period_end=1)


# --- 5. Invalid period range -------------------------------------------------


def test_invalid_period_range_endpoint_is_rejected():
    with pytest.raises(ValidationError, match="out of range"):
        ScheduleFactory(period_start=6, period_end=9)


# --- 6. period_start > period_end rejected -----------------------------------


def test_period_start_after_end_is_rejected():
    with pytest.raises(ValidationError, match="must be <="):
        ScheduleFactory(period_start=3, period_end=2)


# --- 7. Lunch cannot be scheduled --------------------------------------------


def test_lunch_is_not_a_teaching_period():
    # Lunch has no period number, so it can never be represented / scheduled.
    assert LUNCH_AFTER_PERIOD == 4
    assert TEACHING_PERIODS == (1, 2, 3, 4, 5, 6, 7)

    structure = describe_period_structure()
    lunch_entries = [s for s in structure if s["is_lunch"]]
    assert len(lunch_entries) == 1
    assert lunch_entries[0]["period"] is None
    # Lunch sits right after Hour 4.
    labels = [s["label"] for s in structure]
    assert labels.index("LUNCH") == labels.index("Hour 4") + 1


def test_non_numeric_lunch_period_is_rejected():
    with pytest.raises(ValidationError):
        ScheduleFactory(period_start="LUNCH", period_end="LUNCH")


# --- 8. Same faculty overlapping periods rejected ----------------------------


def test_same_faculty_overlapping_periods_rejected(db):
    fac, crs = _run(_seed(db))
    crs2 = _run(
        db.courses.insert_one(
            {
                "course_code": "CS102",
                "course_name": "Another",
                "department": "CSE",
                "semester": 1,
                "credits": 3,
                "faculty_id": fac,
            }
        )
    )

    _run(
        create_timetable(
            _payload(
                fac,
                crs,
                [{"day": "Monday", "period_start": 4, "period_end": 5}],
            )
        )
    )

    # A different timetable for the SAME faculty clashing on Monday Hour 5-6.
    with pytest.raises(ValueError, match="Faculty already has a timetable slot"):
        _run(
            create_timetable(
                _payload(
                    fac,
                    crs2.inserted_id,
                    [{"day": "Monday", "period_start": 5, "period_end": 6}],
                )
            )
        )


def test_different_faculty_same_period_is_allowed(db):
    fac1, crs1 = _run(_seed(db, faculty_id="FAC001", course_code="CS101"))
    fac2, crs2 = _run(_seed(db, faculty_id="FAC002", course_code="CS201"))

    _run(
        create_timetable(
            _payload(fac1, crs1, [{"day": "Monday", "period_start": 5, "period_end": 6}])
        )
    )
    # Same slot, different faculty -> allowed.
    _run(
        create_timetable(
            _payload(fac2, crs2, [{"day": "Monday", "period_start": 5, "period_end": 6}])
        )
    )
    assert _run(db.timetables.count_documents({})) == 2


# --- 9. Same timetable overlapping periods rejected --------------------------


def test_same_timetable_overlapping_periods_rejected(db):
    fac, crs = _run(_seed(db))
    with pytest.raises(ValidationError, match="Overlapping periods"):
        _payload(
            fac,
            crs,
            [
                {"day": "Thursday", "period_start": 4, "period_end": 5},
                {"day": "Thursday", "period_start": 5, "period_end": 6},
            ],
        )


def test_same_timetable_non_overlapping_adjacent_is_allowed(db):
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(
                fac,
                crs,
                [
                    {"day": "Thursday", "period_start": 1, "period_end": 2},
                    {"day": "Thursday", "period_start": 3, "period_end": 4},
                ],
            )
        )
    )
    stored = _run(get_timetable(timetable_id))
    assert len(stored["schedule"]) == 2


# --- 10. Monday-Saturday supported -------------------------------------------


def test_all_weekdays_monday_to_saturday_supported(db):
    fac, crs = _run(_seed(db))
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    timetable_id = _run(
        create_timetable(
            _payload(
                fac,
                crs,
                [{"day": d, "period_start": 1, "period_end": 1} for d in days],
            )
        )
    )
    stored = _run(get_timetable(timetable_id))
    assert {s["day"] for s in stored["schedule"]} == set(days)


def test_sunday_is_rejected():
    with pytest.raises(ValidationError, match="Invalid weekday"):
        ScheduleFactory(day="Sunday", period_start=1, period_end=1)


# --- 11. Course/faculty relationships validated ------------------------------


def test_nonexistent_faculty_is_rejected(db):
    _, crs = _run(_seed(db))
    with pytest.raises(ValueError, match="Faculty not found"):
        _run(
            create_timetable(
                _payload(
                    ObjectId(),  # valid id, no such faculty
                    crs,
                    [{"day": "Monday", "period_start": 1, "period_end": 1}],
                )
            )
        )


def test_nonexistent_course_is_rejected(db):
    fac, _ = _run(_seed(db))
    with pytest.raises(ValueError, match="Course not found"):
        _run(
            create_timetable(
                _payload(
                    fac,
                    ObjectId(),
                    [{"day": "Monday", "period_start": 1, "period_end": 1}],
                )
            )
        )


def test_semester_mismatch_is_rejected(db):
    fac, crs = _run(_seed(db, semester=1))
    with pytest.raises(ValueError, match="Semester mismatch"):
        _run(
            create_timetable(
                _payload(
                    fac,
                    crs,
                    [{"day": "Monday", "period_start": 1, "period_end": 1}],
                    semester=5,
                )
            )
        )


def test_invalid_faculty_id_is_rejected(db):
    _, crs = _run(_seed(db))
    with pytest.raises(Exception):  # to_object_id -> HTTPException(400)
        _run(
            create_timetable(
                _payload(
                    "not-an-object-id",
                    crs,
                    [{"day": "Monday", "period_start": 1, "period_end": 1}],
                )
            )
        )


# --- 12. Existing clock-time timetable remains readable ----------------------


def test_legacy_clock_time_timetable_remains_readable(db):
    # Simulate a pre-expansion timetable document (day + start_time + end_time).
    result = _run(
        db.timetables.insert_one(
            {
                "faculty_id": "FAC-LEGACY",
                "course_id": "CRS-LEGACY",
                "semester": 1,
                "schedule": [
                    {"day": "Monday", "start_time": "09:00", "end_time": "09:50"}
                ],
            }
        )
    )
    stored = _run(get_timetable(str(result.inserted_id)))
    assert stored is not None
    assert stored["schedule"][0]["start_time"] == "09:00"
    # Legacy string references pass through unchanged.
    assert stored["faculty_id"] == "FAC-LEGACY"


def test_legacy_clock_time_slot_is_accepted_by_schema(db):
    fac, crs = _run(_seed(db))
    # A new record may still use clock times for backward compatibility.
    timetable_id = _run(
        create_timetable(
            _payload(
                fac,
                crs,
                [{"day": "Monday", "start_time": "09:00", "end_time": "09:50"}],
            )
        )
    )
    stored = _run(get_timetable(timetable_id))
    assert stored["schedule"][0]["end_time"] == "09:50"
    assert stored["schedule"][0]["period_start"] is None


def test_slot_without_periods_or_clock_is_rejected():
    with pytest.raises(ValidationError, match="either period_start"):
        ScheduleFactory(day="Monday")


# --- 13. New period-based timetable stored correctly -------------------------


def test_new_period_timetable_stored_with_object_id_refs(db):
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(fac, crs, [{"day": "Monday", "period_start": 1, "period_end": 2}])
        )
    )
    raw = _run(db.timetables.find_one({"_id": ObjectId(timetable_id)}))
    assert isinstance(raw["faculty_id"], ObjectId)
    assert isinstance(raw["course_id"], ObjectId)
    assert raw["schedule"][0]["period_start"] == 1


# --- 14. GET all timetables --------------------------------------------------


def test_get_all_timetables(db):
    fac, crs = _run(_seed(db))
    _run(
        create_timetable(
            _payload(fac, crs, [{"day": "Monday", "period_start": 1, "period_end": 1}])
        )
    )
    all_tt = _run(get_all_timetables())
    assert len(all_tt) == 1
    assert isinstance(all_tt[0]["_id"], str)
    assert isinstance(all_tt[0]["faculty_id"], str)


# --- 15. GET single timetable ------------------------------------------------


def test_get_single_timetable(db):
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(fac, crs, [{"day": "Monday", "period_start": 1, "period_end": 1}])
        )
    )
    assert _run(get_timetable(timetable_id)) is not None
    assert _run(get_timetable(str(ObjectId()))) is None
    assert _run(get_timetable("not-a-valid-id")) is None


# --- 16. UPDATE timetable ----------------------------------------------------


def test_update_timetable_schedule(db):
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(fac, crs, [{"day": "Monday", "period_start": 1, "period_end": 1}])
        )
    )

    modified = _run(
        update_timetable(
            timetable_id,
            TimetableUpdate(
                schedule=[{"day": "Friday", "period_start": 6, "period_end": 7}]
            ),
        )
    )
    assert modified == 1

    updated = _run(get_timetable(timetable_id))
    assert updated["schedule"][0]["day"] == "Friday"
    assert updated["schedule"][0]["period_start"] == 6


def test_update_nonexistent_timetable_returns_zero(db):
    modified = _run(
        update_timetable(
            str(ObjectId()),
            TimetableUpdate(semester=2),
        )
    )
    assert modified == 0


def test_update_timetable_does_not_self_conflict(db):
    # Re-saving an overlapping-looking schedule for the SAME document must not
    # flag the document against itself.
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(fac, crs, [{"day": "Monday", "period_start": 1, "period_end": 2}])
        )
    )
    # The update must be ACCEPTED (no ScheduleConflictError raised against the
    # document itself). ``modified_count`` is an implementation detail — when the
    # re-saved values and the ``updated_at`` timestamp are byte-identical Mongo
    # legitimately reports 0 modified — so the real contract is asserted via the
    # persisted state below rather than the exact modified count.
    modified = _run(
        update_timetable(
            timetable_id,
            TimetableUpdate(
                schedule=[{"day": "Monday", "period_start": 1, "period_end": 2}]
            ),
        )
    )
    assert modified in (0, 1)

    persisted = _run(get_timetable(timetable_id))
    assert persisted["schedule"][0]["day"] == "Monday"
    assert persisted["schedule"][0]["period_start"] == 1
    assert persisted["schedule"][0]["period_end"] == 2


# --- 17. DELETE timetable ----------------------------------------------------


def test_delete_timetable(db):
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(fac, crs, [{"day": "Monday", "period_start": 1, "period_end": 1}])
        )
    )
    assert _run(delete_timetable(timetable_id)) == 1
    assert _run(get_timetable(timetable_id)) is None


def test_delete_nonexistent_timetable_returns_zero(db):
    assert _run(delete_timetable(str(ObjectId()))) == 0
    assert _run(delete_timetable("not-a-valid-id")) == 0


# --- 18. Special timetable-day compatibility ---------------------------------


def test_special_timetable_day_lookup(db):
    # Calendar Task #3 maps e.g. 17.08.2026 -> "Thursday" timetable. The next
    # scheduler task will use that mapping to fetch the Thursday entries from a
    # timetable; verify the isolated helper returns exactly those entries.
    fac, crs = _run(_seed(db))
    timetable_id = _run(
        create_timetable(
            _payload(
                fac,
                crs,
                [
                    {"day": "Thursday", "period_start": 1, "period_end": 2},
                    {"day": "Friday", "period_start": 3, "period_end": 4},
                ],
            )
        )
    )
    stored = _run(get_timetable(timetable_id))

    thursday = entries_for_timetable_day(stored["schedule"], "Thursday")
    assert len(thursday) == 1
    assert thursday[0]["period_start"] == 1

    # Alias / case-insensitive weekday still resolves (17.08.2026 -> "thu").
    assert len(entries_for_timetable_day(stored["schedule"], "thu")) == 1
    # Friday swap (12.09.2026 -> "friday").
    assert len(entries_for_timetable_day(stored["schedule"], "friday")) == 1


def ScheduleFactory(**overrides):
    """Build a single ``ScheduleItem`` for validation-focused tests.

    Defined last so the test bodies above can reference it; it simply
    round-trips through ``TimetableCreate``'s item schema.
    """
    from app.schemas.timetable_schema import ScheduleItem

    payload = {"day": "Monday"}
    payload.update(overrides)
    return ScheduleItem(**payload)
