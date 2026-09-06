"""Domain rules for scheduling and academic calendar configuration.

This module centralizes all constraints, limits, and statuses related to
teaching days, examinations, and hours, preventing hard-coded magic values
scattered throughout the scheduler engine.
"""

from enum import Enum


class DayType(str, Enum):
    """The nature of the teaching day (normal vs. exam days)."""
    NORMAL = "normal"
    CIA = "cia"


class ScheduleType(str, Enum):
    """The type of a scheduled session block."""
    CLASS = "class"
    EXAM = "exam"


class ExamType(str, Enum):
    """Specific exam events that might trigger CIA day logic."""
    CIA_I = "cia-I"
    CIA_II = "cia-II"
    CIA_III = "cia-III"
    UNIT_TEST = "unit_test"
    MODEL_EXAM = "model_exam"
    MODEL_PRACTICAL = "model_practical"
    MODEL_THEORY = "model_theory"
    SEMESTER_END_PRACTICAL = "semester_end_practical"
    SEMESTER_END_THEORY = "semester_end_theory"


class WorkingStatus(str, Enum):
    """Whether a day is a working college day or a holiday."""
    WORKING = "working"
    HOLIDAY = "holiday"


# --- Hour Limits and Rules ---

# Total Schedulable Hours per Weekday.
# A standard college day is 7 hours. Saturday is a half day (4 hours).
MAX_HOURS_PER_DAY: dict[str, int] = {
    "Monday": 7,
    "Tuesday": 7,
    "Wednesday": 7,
    "Thursday": 7,
    "Friday": 7,
    "Saturday": 4,
    "Sunday": 0
}

# Specific hours that are never schedulable on a Saturday (e.g. afternoon).
SATURDAY_EXCLUDED_HOURS: tuple[int, ...] = (5, 6, 7)

# On a CIA exam day, the designated exam periods (e.g., Hour 1 and Hour 2).
# The remaining allowed hours for that day (up to its MAX_HOURS_PER_DAY)
# will be normal classes.
CIA_EXAM_PERIODS: tuple[int, ...] = (1, 2)
