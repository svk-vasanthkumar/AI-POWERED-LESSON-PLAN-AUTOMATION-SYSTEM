"""Deterministic unit tests for the calendar-aware, period-based scheduler
engine additions (Task #5).

Pure in-memory data only — no MongoDB, no Groq — so they run anywhere and prove
the new scheduling decisions are correct and deterministic:

  * teachable-day construction (blocked ranges + working days),
  * special / swap timetable days,
  * period-slot grouping (single + multi-period lab blocks),
  * period allocation across days (lunch never scheduled),
  * legacy clock-time allocation through the same block allocator,
  * unscheduled overflow reporting,
  * period-based and clock-based conflict detection.

Run: python -m pytest backend/tests/test_scheduler_engine_periods.py -q
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app.services import scheduler_engine as se
from app.services.scheduler_engine import SchedulerValidationError

WORKING = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def make_topics(*specs):
    """specs = (topic_id, title, hours) -> extract_topics output shape."""
    return se.extract_topics(
        {
            "units": [
                {
                    "unit_number": 1,
                    "unit_title": "U1",
                    "topics": [
                        {"topic_id": tid, "topic": title, "estimated_hours": hours}
                        for tid, title, hours in specs
                    ],
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# Teachable days (req. 2-3)
# ---------------------------------------------------------------------------

def test_teachable_days_skip_weekends_and_blocked():
    # 2026-07-27 is Monday .. 2026-08-02 is Sunday.
    days = se.build_teachable_days(
        "2026-07-27",
        "2026-08-02",
        WORKING,
        blocked_dates={date(2026, 7, 29)},  # Wednesday holiday
    )
    iso = [d.isoformat() for d, _ in days]
    # Sunday (Aug 2) not a working day; Wed blocked; Sat IS a working day here.
    assert iso == [
        "2026-07-27", "2026-07-28", "2026-07-30", "2026-07-31", "2026-08-01"
    ]
    # Effective weekday equals the real weekday when there is no swap.
    assert days[0] == (date(2026, 7, 27), "Monday")


def test_special_day_swaps_effective_weekday():
    # Make Monday 2026-07-27 follow the Thursday timetable.
    days = se.build_teachable_days(
        "2026-07-27",
        "2026-07-27",
        WORKING,
        special_days=[{"date": "2026-07-27", "timetable_day": "Thursday"}],
    )
    assert days == [(date(2026, 7, 27), "Thursday")]


def test_blocked_beats_special_day():
    # A swap day that is also blocked must NOT be teachable.
    with pytest.raises(SchedulerValidationError):
        days = se.build_teachable_days(
            "2026-07-27",
            "2026-07-27",
            WORKING,
            blocked_dates={date(2026, 7, 27)},
            special_days=[{"date": "2026-07-27", "timetable_day": "Thursday"}],
        )


def test_teachable_days_invalid_range():
    with pytest.raises(SchedulerValidationError):
        se.build_teachable_days("2026-08-01", "2026-07-01", WORKING)


def test_teachable_days_no_working_days():
    with pytest.raises(SchedulerValidationError):
        se.build_teachable_days("2026-07-27", "2026-07-31", [])


# ---------------------------------------------------------------------------
# Period slot grouping (req. 4-5)
# ---------------------------------------------------------------------------

def test_period_slots_grouped_and_sorted():
    schedule = [
        {"day": "Monday", "period_start": 3, "period_end": 3},
        {"day": "Monday", "period_start": 1, "period_end": 2},  # lab block
        {"day": "Tuesday", "period_start": 5, "period_end": 5},
    ]
    slots = se.build_period_slots_by_weekday(schedule)
    assert slots["Monday"] == [(1, 2), (3, 3)]  # sorted by start
    assert slots["Tuesday"] == [(5, 5)]


def test_period_slots_reject_out_of_range():
    with pytest.raises(SchedulerValidationError):
        se.build_period_slots_by_weekday(
            [{"day": "Monday", "period_start": 6, "period_end": 8}]
        )


def test_period_slots_reject_reversed_range():
    with pytest.raises(SchedulerValidationError):
        se.build_period_slots_by_weekday(
            [{"day": "Monday", "period_start": 4, "period_end": 2}]
        )


def test_timetable_is_period_based_detection():
    assert se.timetable_is_period_based(
        [{"day": "Monday", "period_start": 1, "period_end": 1}]
    )
    assert not se.timetable_is_period_based(
        [{"day": "Monday", "start_time": "09:00", "end_time": "10:00"}]
    )


# ---------------------------------------------------------------------------
# Period allocation (req. 6, 10) — lunch never scheduled
# ---------------------------------------------------------------------------

def test_period_allocation_single_periods_across_days():
    topics = make_topics(("T1", "A", 2), ("T2", "B", 1))  # 3 single periods
    days = se.build_teachable_days("2026-07-27", "2026-07-28", ["Monday", "Tuesday"])
    slots = se.build_period_slots_by_weekday(
        [
            {"day": "Monday", "period_start": 1, "period_end": 1},
            {"day": "Monday", "period_start": 2, "period_end": 2},
            {"day": "Tuesday", "period_start": 5, "period_end": 5},
        ]
    )
    blocks = se.build_period_blocks(days, slots)
    sessions, unscheduled = se.allocate_blocks(topics, blocks)

    assert unscheduled == []
    laid = [
        (s["date"], s["topic"], s["period_start"], s["period_end"]) for s in sessions
    ]
    assert laid == [
        ("2026-07-27", "A", 1, 2),
        ("2026-07-28", "B", 5, 5),
    ]
    # Period 5 is AFTER lunch — proving lunch (between 4 and 5) is never a slot.
    assert sessions[0]["duration_hours"] == 2
    assert sessions[1]["duration_hours"] == 1


def test_multi_period_lab_block_stays_single_session():
    # A 3h topic poured into a Hour 3-5 lab block (spans lunch, counts 3 periods).
    topics = make_topics(("T1", "Lab", 3))
    days = se.build_teachable_days("2026-07-27", "2026-07-27", ["Monday"])
    slots = se.build_period_slots_by_weekday(
        [{"day": "Monday", "period_start": 3, "period_end": 5}]
    )
    blocks = se.build_period_blocks(days, slots)
    sessions, unscheduled = se.allocate_blocks(topics, blocks)

    assert unscheduled == []
    assert len(sessions) == 1
    assert sessions[0]["period_start"] == 3
    assert sessions[0]["period_end"] == 5
    assert sessions[0]["duration_hours"] == 3


def test_period_block_holds_tail_and_head_of_two_topics():
    # A=2h then B=1h into a single Hour 1-3 block: A takes periods 1-2, B period 3.
    topics = make_topics(("T1", "A", 2), ("T2", "B", 1))
    days = se.build_teachable_days("2026-07-27", "2026-07-27", ["Monday"])
    slots = se.build_period_slots_by_weekday(
        [{"day": "Monday", "period_start": 1, "period_end": 3}]
    )
    blocks = se.build_period_blocks(days, slots)
    sessions, _ = se.allocate_blocks(topics, blocks)

    assert [(s["topic"], s["period_start"], s["period_end"]) for s in sessions] == [
        ("A", 1, 2),
        ("B", 3, 3),
    ]


def test_period_times_attached_when_configured():
    time_map = {
        1: {"start_time": "09:00", "end_time": "09:50"},
        2: {"start_time": "09:50", "end_time": "10:40"},
    }
    topics = make_topics(("T1", "A", 2))
    days = se.build_teachable_days("2026-07-27", "2026-07-27", ["Monday"])
    slots = se.build_period_slots_by_weekday(
        [{"day": "Monday", "period_start": 1, "period_end": 2}]
    )
    blocks = se.build_period_blocks(days, slots, period_time_map=time_map)
    sessions, _ = se.allocate_blocks(topics, blocks)
    assert sessions[0]["start_time"] == "09:00"
    assert sessions[0]["end_time"] == "10:40"


def test_period_unscheduled_overflow():
    topics = make_topics(("T1", "A", 5))
    days = se.build_teachable_days("2026-07-27", "2026-07-27", ["Monday"])
    slots = se.build_period_slots_by_weekday(
        [{"day": "Monday", "period_start": 1, "period_end": 2}]
    )
    blocks = se.build_period_blocks(days, slots)
    sessions, unscheduled = se.allocate_blocks(topics, blocks)
    assert sum(s["duration_hours"] for s in sessions) == 2
    assert unscheduled and unscheduled[0]["remaining_hours"] == 3.0


# ---------------------------------------------------------------------------
# Legacy clock allocation through the same allocator (req. 12)
# ---------------------------------------------------------------------------

def test_clock_blocks_allocation_backward_compatible():
    topics = make_topics(("T1", "A", 1.5), ("T2", "B", 0.5))
    days = se.build_teachable_days("2026-07-27", "2026-07-27", ["Monday"])
    clock_slots = se.build_slots_by_weekday(
        [{"day": "Monday", "start_time": "09:00", "end_time": "11:00"}]
    )
    blocks = se.build_clock_blocks(days, clock_slots)
    sessions, unscheduled = se.allocate_blocks(topics, blocks)
    assert unscheduled == []
    assert (sessions[0]["start_time"], sessions[0]["end_time"]) == ("09:00", "10:30")
    assert (sessions[1]["start_time"], sessions[1]["end_time"]) == ("10:30", "11:00")


# ---------------------------------------------------------------------------
# Conflict detection (req. 8)
# ---------------------------------------------------------------------------

def test_period_conflict_detection_same_date_overlap():
    new = [{"date": "2026-07-27", "day": "Monday", "period_start": 2,
            "period_end": 3, "topic": "A"}]
    existing = [{"date": "2026-07-27", "period_start": 3, "period_end": 4,
                 "reason": "Faculty busy"}]
    conflicts = se.detect_session_conflicts(new, existing)
    assert len(conflicts) == 1
    assert conflicts[0]["reason"] == "Faculty busy"
    assert conflicts[0]["new_slot"] == "Hour 2-3"


def test_period_no_conflict_when_periods_disjoint():
    new = [{"date": "2026-07-27", "period_start": 1, "period_end": 2, "topic": "A"}]
    existing = [{"date": "2026-07-27", "period_start": 3, "period_end": 4}]
    assert se.detect_session_conflicts(new, existing) == []


def test_no_conflict_on_different_date():
    new = [{"date": "2026-07-27", "period_start": 1, "period_end": 2, "topic": "A"}]
    existing = [{"date": "2026-07-28", "period_start": 1, "period_end": 2}]
    assert se.detect_session_conflicts(new, existing) == []


def test_clock_conflict_detection_via_new_function():
    new = [{"date": "2026-07-27", "start_time": "09:00", "end_time": "10:00",
            "topic": "A"}]
    existing = [{"date": "2026-07-27", "start_time": "09:30", "end_time": "10:30",
                 "reason": "busy"}]
    assert len(se.detect_session_conflicts(new, existing)) == 1


def test_period_and_clock_are_not_compared():
    # A period session and a clock session on the same date are non-comparable
    # and must not be reported as a conflict.
    new = [{"date": "2026-07-27", "period_start": 1, "period_end": 2, "topic": "A"}]
    existing = [{"date": "2026-07-27", "start_time": "09:00", "end_time": "10:00"}]
    assert se.detect_session_conflicts(new, existing) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
