"""End-to-end parsing tests for the real Adhiyamaan College of Engineering
(ACE) 2026-2027 ODD-semester academic calendar.

These tests lock in the fixes for the issues the actual uploaded document
exposed:

  1. ``working_days`` is no longer empty.
  2. All nine special-timetable substitutions are preserved.
  3. Single-date events stay single-date (no accidental ranges).
  4. Date-range events stay ranges, each with its OWN dates.
  5. CIA events are normalised with no duplicates despite inconsistent
     spacing/capitalisation in the source.
  6. ``timetable_day`` is the timetable to APPLY, not the real weekday.

The fixture below mirrors the structure and wording of the source document,
including its inconsistent CIA spacing ("- III", "-III", "-II", "- II").
"""

from datetime import date

import pytest

from app.services.academic_calendar_parser import parse_academic_calendar_text

# Wording/spacing intentionally mirrors the messy source (mixed "- III"/"-III",
# "Report Submission"/"Report submission") so the normalisation is exercised.
ACE_2026_2027_RAW = """Adhiyamaan College of Engineering (An Autonomous Institution)
Academic Schedule (UG&PG) III, IV year B.E/B.Tech 2026-2027 (ODD Semester)
Commencement of V, VII & IX (Arch) Semester Classes 01.07.2026

04.07.2026 - Tuesday Timetable
06.07.2026 - Wednesday Timetable
11.07.2026 - Thursday Timetable
13.07.2026 - Friday Timetable
18.07.2026 - Tuesday Timetable
20.07.2026 - Wednesday Timetable
17.08.2026 - Thursday Timetable
12.09.2026 - Friday Timetable
10.10.2026 - Tuesday Timetable

Last Date for Course Registration 13.07.2026
Confirmation of Course Registration 25.07.2026
Continuous Internal Assessment - I 25.07.2026 to 10.08.2026
Continuous Internal Assessment -I Report Submission 17.08.2026
Continuous Internal Assessment - II 22.08.2026 to 07.09.2026
Continuous Internal Assessment -II Report Submission 12.09.2026
Continuous Internal Assessment -III 19.09.2026 to 05.10.2026
Continuous Internal Assessment - III Report submission 10.10.2026
Last Day for Payment of Examination Fee 10.10.2026
Model practical Examination 12.10.2026 to 14.10.2026
Remedial / Revision Classes 15.10.2026 to 17.10.2026
Publication of End Semester Timetable 17.10.2026
Model Theory Examination 22.10.2026 to 28.10.2026
Last Working Day 28.10.2026
Semester End Practical Examinations 30.10.2026 to 07.11.2026
Issue of Hall tickets 10.11.2026
Last Date for submission of IA Report / CO Attainment 11.11.2026
Semester End Theory Examinations 16.11.2026 to 23.12.2026
Winter Vacation 24.12.2026 to 03.01.2027
Commencement of EVEN Semester Classes 04.01.2027

15.08.2026 - Independence Day
26.08.2026 - Milad-un-Nabi
04.09.2026 - Krishna Jayanthi
14.09.2026 - Vinayakar Chathurthi
02.10.2026 - Gandhi Jayanthi
20.10.2026 - Ayutha Pooja
21.10.2026 - Vijaya Dasami
09.11.2026 - Deepavali
25.12.2026 - Christmas

Month Working Days
July 27
August 25
September 25
October 19
Total No. of Working Days 96
"""


@pytest.fixture()
def calendar():
    return parse_academic_calendar_text(
        ACE_2026_2027_RAW,
        original_filename="ACE_2026_2027_ODD.pdf",
        extraction_method="text",
    )


def _events_by_type(calendar, event_type):
    return [event for event in calendar.events if event.type == event_type]


def _single_event(calendar, event_type):
    matches = _events_by_type(calendar, event_type)
    assert len(matches) == 1, f"expected exactly one {event_type}, got {len(matches)}"
    return matches[0]


# --- Identity ---------------------------------------------------------------


def test_academic_year(calendar):
    assert calendar.academic_year == "2026-2027"


def test_semester(calendar):
    assert calendar.semester == 7


def test_semester_start_and_end(calendar):
    assert calendar.semester_start == date(2026, 7, 1)
    # Anchored to the end of Semester End Theory, not the EVEN commencement.
    assert calendar.semester_end == date(2026, 12, 23)


# --- Working days -----------------------------------------------------------


def test_working_days_not_empty(calendar):
    assert calendar.working_days, "working_days must not be empty"


def test_working_days_is_six_day_week(calendar):
    # ACE runs a Mon–Sat week; the Saturday substitution rows prove Saturday is
    # a working day, and Sunday is never a working day here.
    assert calendar.working_days == [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
    ]


def test_monthly_working_days_counts(calendar):
    counts = {item.month: item.working_days for item in calendar.monthly_working_days}
    assert counts == {
        "July": 27,
        "August": 25,
        "September": 25,
        "October": 19,
    }


def test_total_working_days_is_96(calendar):
    assert calendar.total_working_days == 96
    # The official total is preserved as its own field, distinct from the
    # per-month counts (which happen to sum to the same 96 here).
    assert sum(item.working_days for item in calendar.monthly_working_days) == 96


# --- Holidays ---------------------------------------------------------------


def test_all_holidays_present(calendar):
    holidays = {holiday.date: holiday.name for holiday in calendar.holidays}
    assert holidays == {
        date(2026, 8, 15): "Independence Day",
        date(2026, 8, 26): "Milad-un-Nabi",
        date(2026, 9, 4): "Krishna Jayanthi",
        date(2026, 9, 14): "Vinayakar Chathurthi",
        date(2026, 10, 2): "Gandhi Jayanthi",
        date(2026, 10, 20): "Ayutha Pooja",
        date(2026, 10, 21): "Vijaya Dasami",
        date(2026, 11, 9): "Deepavali",
        date(2026, 12, 25): "Christmas",
    }


# --- Special timetable substitutions ----------------------------------------


def test_all_nine_special_timetable_days(calendar):
    special = {item.date: item.timetable_day for item in calendar.special_days}
    assert special == {
        date(2026, 7, 4): "Tuesday",
        date(2026, 7, 6): "Wednesday",
        date(2026, 7, 11): "Thursday",
        date(2026, 7, 13): "Friday",
        date(2026, 7, 18): "Tuesday",
        date(2026, 7, 20): "Wednesday",
        date(2026, 8, 17): "Thursday",
        date(2026, 9, 12): "Friday",
        date(2026, 10, 10): "Tuesday",
    }
    assert len(calendar.special_days) == 9


def test_timetable_day_is_not_the_real_weekday(calendar):
    # 04.07.2026 is a real Saturday, but its timetable_day must stay "Tuesday"
    # (the timetable to APPLY that day), never the calendar weekday.
    entry = next(s for s in calendar.special_days if s.date == date(2026, 7, 4))
    assert entry.timetable_day == "Tuesday"
    assert date(2026, 7, 4).strftime("%A") == "Saturday"


# --- Single-date events -----------------------------------------------------


@pytest.mark.parametrize(
    "event_type,expected_date",
    [
        ("course_registration", date(2026, 7, 13)),
        ("course_registration_confirmation", date(2026, 7, 25)),
        ("exam_fee", date(2026, 10, 10)),
        ("end_semester_timetable", date(2026, 10, 17)),
        ("last_working_day", date(2026, 10, 28)),
        ("hall_ticket", date(2026, 11, 10)),
        ("ia_report", date(2026, 11, 11)),
        ("even_semester_commencement", date(2027, 1, 4)),
    ],
)
def test_single_date_events(calendar, event_type, expected_date):
    event = _single_event(calendar, event_type)
    assert event.date == expected_date
    assert event.start_date is None
    assert event.end_date is None


def test_cia_report_submissions_are_single_dates(calendar):
    reports = _events_by_type(calendar, "cia_report")
    by_date = sorted(event.date for event in reports)
    assert by_date == [date(2026, 8, 17), date(2026, 9, 12), date(2026, 10, 10)]
    for event in reports:
        assert event.start_date is None and event.end_date is None


# --- Date-range events ------------------------------------------------------


@pytest.mark.parametrize(
    "event_type,start,end",
    [
        ("model_practical", date(2026, 10, 12), date(2026, 10, 14)),
        ("remedial", date(2026, 10, 15), date(2026, 10, 17)),
        ("model_theory", date(2026, 10, 22), date(2026, 10, 28)),
        ("semester_end_practical", date(2026, 10, 30), date(2026, 11, 7)),
        ("semester_end_theory", date(2026, 11, 16), date(2026, 12, 23)),
        ("winter_vacation", date(2026, 12, 24), date(2027, 1, 3)),
    ],
)
def test_date_range_events(calendar, event_type, start, end):
    event = _single_event(calendar, event_type)
    assert event.start_date == start
    assert event.end_date == end
    assert event.date is None


def test_cia_exam_ranges(calendar):
    cia = _events_by_type(calendar, "cia")
    ranges = sorted((event.start_date, event.end_date) for event in cia)
    assert ranges == [
        (date(2026, 7, 25), date(2026, 8, 10)),
        (date(2026, 8, 22), date(2026, 9, 7)),
        (date(2026, 9, 19), date(2026, 10, 5)),
    ]
    for event in cia:
        assert event.date is None


def test_no_neighbouring_range_bleed_into_single_events(calendar):
    # CIA-I Report (single, 17.08) sits right after CIA-I (range). It must not
    # inherit the range's dates.
    report = next(
        event
        for event in _events_by_type(calendar, "cia_report")
        if event.date == date(2026, 8, 17)
    )
    assert report.start_date is None and report.end_date is None


# --- CIA de-duplication / normalisation -------------------------------------


def test_no_duplicate_cia_events(calendar):
    cia = _events_by_type(calendar, "cia")
    assert len(cia) == 3
    names = sorted(event.name for event in cia)
    assert names == [
        "Continuous Internal Assessment - I",
        "Continuous Internal Assessment - II",
        "Continuous Internal Assessment - III",
    ]


def test_cia_report_names_are_normalised(calendar):
    reports = _events_by_type(calendar, "cia_report")
    assert len(reports) == 3
    names = sorted(event.name for event in reports)
    assert names == [
        "Continuous Internal Assessment - I Report Submission",
        "Continuous Internal Assessment - II Report Submission",
        "Continuous Internal Assessment - III Report Submission",
    ]


# --- Other required events --------------------------------------------------


def test_winter_vacation_event(calendar):
    event = _single_event(calendar, "winter_vacation")
    assert event.start_date == date(2026, 12, 24)
    assert event.end_date == date(2027, 1, 3)


def test_even_semester_commencement_event(calendar):
    event = _single_event(calendar, "even_semester_commencement")
    assert event.date == date(2027, 1, 4)


# --- Integrity / determinism ------------------------------------------------


def test_raw_text_is_preserved(calendar):
    assert calendar.raw_text == ACE_2026_2027_RAW


def test_parsing_is_deterministic():
    first = parse_academic_calendar_text(ACE_2026_2027_RAW)
    second = parse_academic_calendar_text(ACE_2026_2027_RAW)
    assert first.model_dump() == second.model_dump()
