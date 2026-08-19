"""Isolated helpers for academic-calendar date handling.

Kept deliberately separate from ``app.services.scheduler_engine`` — this task
(Academic Calendar expansion) must NOT redesign scheduler allocation. These
helpers exist so:

  1. The calendar schema/model can validate weekday values and expand date
     ranges without duplicating ad hoc logic.
  2. The stored document can populate a flattened ``internal_exams`` list so
     the *existing, unmodified* scheduler (which only understands a flat list
     of blocking dates) keeps blocking exam days for calendars created with
     the new structured ranges.
  3. A normalized view of blocked periods / special days is available for the
     NEXT Scheduler task to consume, without wiring it in here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

VALID_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

_VALID_WEEKDAY_SET = frozenset(VALID_WEEKDAYS)

# Accept common short forms, mirroring the aliases the scheduler already
# tolerates in stored data (kept separate on purpose, not imported).
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
    "sun": "Sunday",
}


def normalize_weekday(name) -> str:
    """Normalize a weekday label to canonical Title-case (e.g. ``Monday``).

    Raises ``ValueError`` (not ``HTTPException``) so it can be used directly
    inside Pydantic validators and surface as a clean 422.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Invalid weekday: '{name}'")

    key = name.strip().lower()
    if key in _WEEKDAY_ALIASES:
        return _WEEKDAY_ALIASES[key]

    canonical = key.capitalize()
    if canonical in _VALID_WEEKDAY_SET:
        return canonical

    raise ValueError(f"Invalid weekday: '{name}'")


def to_date(value) -> date:
    """Coerce a value (date/datetime/ISO string) into a ``datetime.date``.

    Raises ``ValueError`` for anything unparseable.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        raw = value.strip().split("T")[0].split(" ")[0]
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    raise ValueError(f"Invalid date: '{value}'")


def to_datetime(value: date | datetime) -> datetime:
    """Convert a ``date`` (or ``datetime``) into a midnight UTC ``datetime``.

    MongoDB has no native ``date`` type, so calendar dates are stored as
    midnight ``datetime`` values, matching how ``created_at``/``updated_at``
    are already stored elsewhere in this project.
    """
    if isinstance(value, datetime):
        return value
    return datetime(value.year, value.month, value.day)


def expand_range_dates(start: date, end: date) -> list[date]:
    """Return every date from ``start`` to ``end`` inclusive."""
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    days = []
    current = start
    one_day = timedelta(days=1)
    while current <= end:
        days.append(current)
        current += one_day
    return days


# Names of the structured exam-type ranges that should also feed the legacy
# flat ``internal_exams`` list so the existing scheduler keeps blocking them.
_EXAM_RANGE_FIELDS = (
    "cia_1",
    "cia_2",
    "cia_3",
    "model_practical",
    "model_theory",
    "semester_end_practical",
    "semester_end_theory",
)


def flatten_exam_range_dates(ranges: dict) -> list[str]:
    """Expand the structured exam-type ranges into a sorted, deduped list of
    ISO date strings.

    ``ranges`` maps field name -> ``{"start_date": date, "end_date": date}``
    (or ``None``) for each of ``_EXAM_RANGE_FIELDS``. Only present, non-``None``
    ranges are expanded.
    """
    dates: set[date] = set()

    for field in _EXAM_RANGE_FIELDS:
        rng = ranges.get(field)
        if not rng:
            continue
        start = to_date(rng["start_date"])
        end = to_date(rng["end_date"])
        dates.update(expand_range_dates(start, end))

    return sorted(d.isoformat() for d in dates)


def normalize_blocked_periods(calendar_doc: dict) -> list[dict]:
    """Return a normalized list of ``{name, start_date, end_date}`` blocked
    periods for a calendar document (new or legacy shape).

    Isolated for the NEXT Scheduler task — not consumed by the current
    scheduler in this task.
    """
    periods: list[dict] = []

    for field in _EXAM_RANGE_FIELDS + ("winter_vacation",):
        rng = calendar_doc.get(field)
        if not rng:
            continue
        periods.append(
            {
                "name": rng.get("name") or field,
                "start_date": to_date(rng["start_date"]),
                "end_date": to_date(rng["end_date"]),
            }
        )

    for rng in calendar_doc.get("blocked_periods") or []:
        periods.append(
            {
                "name": rng.get("name"),
                "start_date": to_date(rng["start_date"]),
                "end_date": to_date(rng["end_date"]),
            }
        )

    return periods


def normalize_special_days(calendar_doc: dict) -> list[dict]:
    """Return ``{date, timetable_day}`` entries for a calendar document.

    Legacy documents (created before this task) have no ``special_days``
    field and simply yield an empty list.
    """
    special_days = []
    for entry in calendar_doc.get("special_days") or []:
        special_days.append(
            {
                "date": to_date(entry["date"]),
                "timetable_day": entry["timetable_day"],
            }
        )
    return special_days
