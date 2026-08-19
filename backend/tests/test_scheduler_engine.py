"""Deterministic unit tests for the pure scheduling engine (Phase 16).

These exercise the algorithm with in-memory stub data only — no MongoDB and no
Groq — so they run anywhere and prove the scheduling decisions are correct and
deterministic.

Run:  python -m pytest backend/tests/test_scheduler_engine.py -q
(or the plain-assert fallback runner at the bottom via `python test_scheduler_engine.py`)
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app.services import scheduler_engine as se
from app.services.scheduler_engine import (
    ScheduleConflictError,
    SchedulerValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_plan():
    return {
        "units": [
            {
                "unit_number": 1,
                "unit_title": "Introduction",
                "topics": [
                    {"topic_id": "U1-T1", "topic": "Topic A", "estimated_hours": 2},
                    {"topic_id": "U1-T2", "topic": "Topic B", "estimated_hours": 1},
                ],
            }
        ]
    }


# semester_start 2026-07-27 is a Monday.
WORKING = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# Timetable: 1-hour slots on Mon/Wed/Fri.
TIMETABLE = [
    {"day": "Monday", "start_time": "09:00", "end_time": "10:00"},
    {"day": "Wednesday", "start_time": "11:00", "end_time": "12:00"},
    {"day": "Friday", "start_time": "14:00", "end_time": "15:00"},
]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_date_formats():
    assert se.parse_date("2026-07-27").isoformat() == "2026-07-27"
    assert se.parse_date("2026-07-27T09:00:00").isoformat() == "2026-07-27"
    assert se.parse_date("27-07-2026").isoformat() == "2026-07-27"


def test_parse_date_invalid():
    with pytest.raises(SchedulerValidationError):
        se.parse_date("not-a-date")


def test_parse_time_and_roundtrip():
    assert se.parse_time_to_minutes("09:30") == 570
    assert se.minutes_to_hhmm(570) == "09:30"
    with pytest.raises(SchedulerValidationError):
        se.parse_time_to_minutes("99:99")


def test_normalize_weekday_aliases():
    assert se.normalize_weekday("mon") == "Monday"
    assert se.normalize_weekday("WEDNESDAY") == "Wednesday"
    with pytest.raises(SchedulerValidationError):
        se.normalize_weekday("Funday")


# ---------------------------------------------------------------------------
# Topic extraction + ordering (Phases 2, 7)
# ---------------------------------------------------------------------------

def test_extract_topics_order():
    topics = se.extract_topics(make_plan())
    assert [t["topic_id"] for t in topics] == ["U1-T1", "U1-T2"]
    assert topics[0]["estimated_hours"] == 2


def test_extract_topics_multi_unit_order():
    plan = {
        "units": [
            {"unit_number": 1, "unit_title": "U1", "topics": [
                {"topic_id": "U1-T1", "topic": "A", "estimated_hours": 1}]},
            {"unit_number": 2, "unit_title": "U2", "topics": [
                {"topic_id": "U2-T1", "topic": "B", "estimated_hours": 1}]},
        ]
    }
    topics = se.extract_topics(plan)
    assert [t["topic_id"] for t in topics] == ["U1-T1", "U2-T1"]


def test_extract_topics_missing_structured_plan_raises():
    # Phase 14 backward compatibility: old plan with no structured_plan.
    with pytest.raises(SchedulerValidationError):
        se.extract_topics(None)
    with pytest.raises(SchedulerValidationError):
        se.extract_topics({"units": []})


# ---------------------------------------------------------------------------
# Available dates (Phases 3-4)
# ---------------------------------------------------------------------------

def test_available_dates_skip_weekends():
    dates = se.build_available_dates(
        "2026-07-27", "2026-08-02", WORKING, [], []
    )
    iso = [d.isoformat() for d in dates]
    # Mon-Fri present, Sat/Sun (Aug 1-2) excluded.
    assert iso == [
        "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"
    ]


def test_available_dates_skip_holiday_and_exam():
    dates = se.build_available_dates(
        "2026-07-27", "2026-07-31", WORKING,
        holidays=["2026-07-29"],  # Wednesday holiday
        internal_exams=["2026-07-31"],  # Friday exam
    )
    iso = [d.isoformat() for d in dates]
    assert "2026-07-29" not in iso
    assert "2026-07-31" not in iso
    assert iso == ["2026-07-27", "2026-07-28", "2026-07-30"]


def test_available_dates_invalid_range():
    with pytest.raises(SchedulerValidationError):
        se.build_available_dates("2026-08-01", "2026-07-01", WORKING, [], [])


# ---------------------------------------------------------------------------
# Slot building (Phase 5)
# ---------------------------------------------------------------------------

def test_build_slots():
    slots = se.build_slots_by_weekday(TIMETABLE)
    assert slots["Monday"] == [(540, 600)]
    assert slots["Friday"] == [(840, 900)]


def test_build_slots_invalid():
    with pytest.raises(SchedulerValidationError):
        se.build_slots_by_weekday(
            [{"day": "Monday", "start_time": "10:00", "end_time": "09:00"}]
        )


# ---------------------------------------------------------------------------
# Allocation: multi-session topic across days (Phases 6-7)
# ---------------------------------------------------------------------------

def test_allocation_basic_multisession():
    topics = se.extract_topics(make_plan())  # A=2h, B=1h
    dates = se.build_available_dates("2026-07-27", "2026-08-07", WORKING, [], [])
    slots = se.build_slots_by_weekday(TIMETABLE)
    sessions, unscheduled = se.allocate_sessions(topics, dates, slots)

    assert unscheduled == []
    # Expected: Mon(A), Wed(A), Fri(B)
    assert [(s["date"], s["topic"]) for s in sessions] == [
        ("2026-07-27", "Topic A"),
        ("2026-07-29", "Topic A"),
        ("2026-07-31", "Topic B"),
    ]
    assert all(s["duration_hours"] == 1 for s in sessions)


def test_allocation_holiday_pushes_topic():
    topics = se.extract_topics(make_plan())  # A=2h, B=1h
    # Wednesday 2026-07-29 is a holiday -> A finishes on Fri, B next Monday.
    dates = se.build_available_dates(
        "2026-07-27", "2026-08-07", WORKING, holidays=["2026-07-29"], internal_exams=[]
    )
    slots = se.build_slots_by_weekday(TIMETABLE)
    sessions, unscheduled = se.allocate_sessions(topics, dates, slots)

    assert unscheduled == []
    assert [(s["date"], s["topic"]) for s in sessions] == [
        ("2026-07-27", "Topic A"),
        ("2026-07-31", "Topic A"),
        ("2026-08-03", "Topic B"),  # next Monday
    ]


def test_allocation_exam_day_has_no_lesson():
    topics = se.extract_topics(make_plan())
    exam_day = "2026-07-31"  # Friday
    dates = se.build_available_dates(
        "2026-07-27", "2026-08-07", WORKING, holidays=[], internal_exams=[exam_day]
    )
    slots = se.build_slots_by_weekday(TIMETABLE)
    sessions, _ = se.allocate_sessions(topics, dates, slots)
    assert all(s["date"] != exam_day for s in sessions)


def test_allocation_slot_holds_two_topics():
    # A 1.5h topic then a 0.5h topic into a single 2h slot.
    plan = {"units": [{"unit_number": 1, "unit_title": "U", "topics": [
        {"topic_id": "U1-T1", "topic": "A", "estimated_hours": 1.5},
        {"topic_id": "U1-T2", "topic": "B", "estimated_hours": 0.5},
    ]}]}
    topics = se.extract_topics(plan)
    dates = se.build_available_dates("2026-07-27", "2026-07-27", ["Monday"], [], [])
    slots = se.build_slots_by_weekday(
        [{"day": "Monday", "start_time": "09:00", "end_time": "11:00"}]
    )
    sessions, unscheduled = se.allocate_sessions(topics, dates, slots)
    assert unscheduled == []
    assert sessions[0]["topic"] == "A"
    assert sessions[0]["start_time"] == "09:00"
    assert sessions[0]["end_time"] == "10:30"
    assert sessions[1]["topic"] == "B"
    assert sessions[1]["start_time"] == "10:30"
    assert sessions[1]["end_time"] == "11:00"


def test_allocation_unscheduled_when_window_too_small():
    plan = {"units": [{"unit_number": 1, "unit_title": "U", "topics": [
        {"topic_id": "U1-T1", "topic": "A", "estimated_hours": 5},
    ]}]}
    topics = se.extract_topics(plan)
    dates = se.build_available_dates("2026-07-27", "2026-07-27", ["Monday"], [], [])
    slots = se.build_slots_by_weekday(
        [{"day": "Monday", "start_time": "09:00", "end_time": "10:00"}]
    )
    sessions, unscheduled = se.allocate_sessions(topics, dates, slots)
    assert len(sessions) == 1
    assert unscheduled and unscheduled[0]["remaining_hours"] == 4.0


# ---------------------------------------------------------------------------
# Conflict detection (Phase 8) + workload (Phase 9)
# ---------------------------------------------------------------------------

def test_conflict_detection():
    new = [{
        "date": "2026-07-27", "day": "Monday",
        "start_time": "09:00", "end_time": "10:00", "topic": "A",
    }]
    existing = [{
        "date": "2026-07-27",
        "start_time": "09:00", "end_time": "10:00", "reason": "Faculty busy",
    }]
    conflicts = se.detect_conflicts(new, existing)
    assert len(conflicts) == 1
    assert conflicts[0]["reason"] == "Faculty busy"


def test_no_conflict_when_no_overlap():
    new = [{
        "date": "2026-07-27", "day": "Monday",
        "start_time": "09:00", "end_time": "10:00", "topic": "A",
    }]
    existing = [{
        "date": "2026-07-27",
        "start_time": "10:00", "end_time": "11:00", "reason": "Adjacent",
    }]
    assert se.detect_conflicts(new, existing) == []


def test_workload_total():
    sessions = [
        {"duration_hours": 1}, {"duration_hours": 1}, {"duration_hours": 0.5}
    ]
    assert se.calculate_total_hours(sessions) == 2.5


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
