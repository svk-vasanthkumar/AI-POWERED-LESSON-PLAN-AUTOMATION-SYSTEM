import pytest
from datetime import date
from app.schemas.academic_calendar_schema import AcademicCalendarCreate
from app.services.calendar_resolver import resolve_date

@pytest.fixture
def sample_calendar():
    return AcademicCalendarCreate(
        academic_year="2023-2024",
        semester=1,
        semester_start=date(2023, 8, 1),
        semester_end=date(2023, 12, 15),
        working_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        holidays=[
            {"date": date(2023, 8, 15), "name": "Independence Day"}
        ],
        special_days=[
            {"date": date(2023, 9, 5), "timetable_day": "Monday"} # Tuesday acting as Monday
        ]
    )

def test_normal_working_day(sample_calendar):
    res = resolve_date(sample_calendar, date(2023, 8, 2)) # Wednesday
    assert res["day"] == "Wednesday"
    assert res["is_working_day"] is True
    assert res["holiday"] is False
    assert res["day_order"] == 3
    assert res["effective_day_order"] == 3
    assert res["special_day_order"] is None
    assert res["effective_day"] == "Wednesday"

def test_holiday_resolution(sample_calendar):
    res = resolve_date(sample_calendar, date(2023, 8, 15)) # Tuesday, Holiday
    assert res["day"] == "Tuesday"
    assert res["is_working_day"] is False
    assert res["holiday"] is True
    assert res["day_order"] == 2
    assert res["effective_day_order"] == 2
    assert res["special_day_order"] is None

def test_special_day_resolution(sample_calendar):
    res = resolve_date(sample_calendar, date(2023, 9, 5)) # Tuesday acting as Monday
    assert res["day"] == "Tuesday"
    assert res["effective_day"] == "Monday"
    assert res["is_working_day"] is True
    assert res["holiday"] is False
    assert res["day_order"] == 2
    assert res["special_day_order"] == 1
    assert res["effective_day_order"] == 1

def test_non_working_day(sample_calendar):
    res = resolve_date(sample_calendar, date(2023, 8, 5)) # Saturday
    assert res["day"] == "Saturday"
    assert res["is_working_day"] is False
    assert res["day_order"] is None
    assert res["effective_day_order"] is None
