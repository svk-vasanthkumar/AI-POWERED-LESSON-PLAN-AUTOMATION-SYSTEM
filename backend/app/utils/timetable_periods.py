"""Canonical college period model + configuration for the faculty timetable.

The college timetable is *period-based*, not clock-based. A teaching day is:

    Hour 1
    Hour 2
    Hour 3
    Hour 4
    LUNCH        <- NOT a teaching period, never schedulable
    Hour 5
    Hour 6
    Hour 7

So the canonical representation of a timetable slot is a weekday plus a
``period_start``/``period_end`` pair (1..7). A single period is
``period_start == period_end``; a lab / multi-period block is
``period_start < period_end``.

Design rules (Task #4):

  * The period <-> clock-time mapping lives HERE (a dedicated timetable
    configuration/utility module), never hard-coded inside the scheduler
    engine.
  * Real college clock times are not available in the current source, so we do
    NOT invent them. Period numbers are the canonical representation; the clock
    mapping is left unconfigured (``None``) and can be populated later via
    :func:`configure_period_times` without touching any other module.
  * Lunch is modelled as a break that sits *after* a configurable teaching
    period (period 4 by default). It has no period number, so the validators
    below make it impossible to ever allocate a class "into lunch".

Everything here is pure (no DB / network), mirroring
``app.utils.calendar_dates`` so it stays unit-testable and reusable by the NEXT
scheduler task without wiring scheduler allocation in now.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Optional

# --- Canonical period structure ---------------------------------------------

#: Lowest / highest teaching period number.
PERIOD_MIN = 1
PERIOD_MAX = 7

#: All teaching period numbers, in order. Lunch is deliberately absent.
TEACHING_PERIODS: tuple[int, ...] = tuple(range(PERIOD_MIN, PERIOD_MAX + 1))

#: Lunch sits *after* this teaching period (between Hour 4 and Hour 5). Lunch is
#: never itself a period number, so it can never be scheduled as a class.
LUNCH_AFTER_PERIOD = 4

#: Weekdays the college timetable runs on (Monday - Saturday). Sunday is
#: intentionally excluded: it is not a teaching day for this timetable.
TIMETABLE_WEEKDAYS: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)

_TIMETABLE_WEEKDAY_SET = frozenset(TIMETABLE_WEEKDAYS)

# Accept common short forms, mirroring the aliases the calendar/scheduler
# helpers already tolerate (kept separate on purpose, not imported).
_WEEKDAY_ALIASES = {
    "mon": "Monday",
    "tue": "Tuesday",
    "tues": "Tuesday",
    "wed": "Wednesday",
    "weds": "Wednesday",
    "thu": "Thursday",
    "thur": "Thursday",
    "thurs": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
}


# --- Period <-> clock-time mapping (configurable, not invented) --------------

# period number -> {"start_time": "HH:MM", "end_time": "HH:MM"}.
# Empty by default: the real college clock times are not available in the
# current source, and we must NOT invent them. Period numbers remain the
# canonical representation until this is configured.
_PERIOD_TIME_MAP: dict[int, dict[str, str]] = {}


def configure_period_times(mapping: dict[int, dict[str, str]]) -> None:
    """Configure the optional period -> clock-time mapping.

    ``mapping`` maps a teaching period number (1..7) to a
    ``{"start_time": "HH:MM", "end_time": "HH:MM"}`` dict. Raises ``ValueError``
    for unknown period numbers so a bad configuration surfaces immediately.

    This exists so real clock times can be supplied later (config / env) without
    changing the scheduler engine or any other module.
    """
    validated: dict[int, dict[str, str]] = {}
    for period, times in mapping.items():
        period_int = int(period)
        if period_int not in TEACHING_PERIODS:
            raise ValueError(
                f"Invalid period number: {period} (expected {PERIOD_MIN}..{PERIOD_MAX})"
            )
        if not isinstance(times, dict) or "start_time" not in times or "end_time" not in times:
            raise ValueError(
                f"Invalid clock time for period {period}: expected "
                "{'start_time': 'HH:MM', 'end_time': 'HH:MM'}"
            )
        validated[period_int] = {
            "start_time": str(times["start_time"]),
            "end_time": str(times["end_time"]),
        }

    global _PERIOD_TIME_MAP
    _PERIOD_TIME_MAP = validated


def get_period_time_map() -> dict[int, dict[str, str]]:
    """Return a copy of the configured period -> clock-time mapping.

    An empty dict means clock times are not configured (period numbers are the
    canonical representation).
    """
    return deepcopy(_PERIOD_TIME_MAP)


def period_to_time_range(period: int) -> Optional[dict[str, str]]:
    """Return ``{"start_time", "end_time"}`` for a period, or ``None`` if the
    clock mapping has not been configured for that period.
    """
    return deepcopy(_PERIOD_TIME_MAP.get(int(period)))


def describe_period_structure() -> list[dict]:
    """Return the ordered canonical day structure (Hour 1..7 with LUNCH).

    Each teaching entry carries its (optional, possibly ``None``) clock times so
    the frontend / next scheduler task can render the college timetable grid
    without hard-coding the layout anywhere.
    """
    structure: list[dict] = []
    for period in TEACHING_PERIODS:
        structure.append(
            {
                "period": period,
                "label": f"Hour {period}",
                "is_lunch": False,
                "times": period_to_time_range(period),
            }
        )
        if period == LUNCH_AFTER_PERIOD:
            structure.append(
                {
                    "period": None,
                    "label": "LUNCH",
                    "is_lunch": True,
                    "times": None,
                }
            )
    return structure


# --- Validation helpers (raise ValueError -> clean 422 in Pydantic) ----------


def normalize_timetable_weekday(name) -> str:
    """Normalize a weekday label to canonical Title-case (``Monday`` ..
    ``Saturday``).

    Raises ``ValueError`` for anything that is not a Monday-Saturday teaching
    day (Sunday included) so it surfaces as a clean 422 in Pydantic validators.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Invalid weekday: '{name}'")

    key = name.strip().lower()
    if key in _WEEKDAY_ALIASES:
        return _WEEKDAY_ALIASES[key]

    canonical = key.capitalize()
    if canonical in _TIMETABLE_WEEKDAY_SET:
        return canonical

    raise ValueError(
        f"Invalid weekday: '{name}' (expected Monday-Saturday)"
    )


def validate_period_number(value, field: str = "period") -> int:
    """Validate a single teaching period number is an integer in 1..7.

    Lunch has no period number, so this doubles as the guarantee that lunch can
    never be represented as a teaching period.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Invalid {field}: '{value}' is not an integer")
    if value < PERIOD_MIN or value > PERIOD_MAX:
        raise ValueError(
            f"Invalid {field}: {value} is out of range "
            f"({PERIOD_MIN}..{PERIOD_MAX})"
        )
    return value


def validate_period_range(period_start: int, period_end: int) -> tuple[int, int]:
    """Validate a ``period_start``/``period_end`` block.

    Enforces both endpoints are valid teaching periods and
    ``period_start <= period_end`` (e.g. ``Hour 3-2`` is rejected). A block may
    span the lunch break (e.g. Hour 3-5 covers Hours 3, 4, 5) because lunch is
    not a numbered period and is simply not counted.
    """
    start = validate_period_number(period_start, "period_start")
    end = validate_period_number(period_end, "period_end")
    if start > end:
        raise ValueError(
            f"Invalid period range: period_start ({start}) must be "
            f"<= period_end ({end})"
        )
    return start, end


def expand_periods(period_start: int, period_end: int) -> list[int]:
    """Return every teaching period number occupied by a block, inclusive.

    ``expand_periods(3, 5) -> [3, 4, 5]``. Lunch is never included because it
    has no period number.
    """
    start, end = validate_period_range(period_start, period_end)
    return list(range(start, end + 1))


def periods_overlap(
    start_a: int, end_a: int, start_b: int, end_b: int
) -> bool:
    """Return ``True`` when two inclusive period blocks share any period."""
    return start_a <= end_b and start_b <= end_a


def entries_for_timetable_day(schedule: list[dict], timetable_day) -> list[dict]:
    """Return the period-based schedule entries for a given weekday.

    Isolated helper for the NEXT scheduler task (and special timetable-day
    swaps such as "17.08.2026 -> Thursday Timetable"): given a stored timetable
    ``schedule`` and a target weekday, return the entries that apply on that
    weekday. Entries with an unparseable / non-matching day are skipped.
    """
    target = normalize_timetable_weekday(timetable_day)
    matched: list[dict] = []
    for entry in schedule or []:
        raw_day = entry.get("day")
        try:
            day = normalize_timetable_weekday(raw_day)
        except ValueError:
            continue
        if day == target:
            matched.append(entry)
    return matched
