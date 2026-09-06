"""Pure, deterministic lesson-scheduling engine.

This module contains **no database or network access**. It takes plain Python
data (a structured lesson plan, an academic-calendar dict, a timetable schedule
list and any pre-existing sessions) and produces a conflict-free, day-wise list
of lesson sessions.

Keeping the algorithm pure makes it fully unit-testable without MongoDB or the
Groq API, and keeps scheduling decisions deterministic (no LLM involvement).

Consumed by ``app.services.scheduler_service`` which handles all persistence.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

# The period model (Hour 1..7, lunch, weekday normalization) is canonical and
# lives in a dedicated, pure utility module. The engine consumes it instead of
# re-declaring period constants, so Task #4's "period config lives in one place"
# rule is preserved. These imports are pure (no DB / network), keeping the
# engine fully unit-testable.
from app.utils.timetable_periods import (
    PERIOD_MAX,
    PERIOD_MIN,
    periods_overlap,
)
from app.utils.scheduling_rules import (
    SATURDAY_EXCLUDED_HOURS,
    CIA_EXAM_PERIODS,
    ScheduleType,
)

# Tiny tolerance so fractional-hour arithmetic (e.g. 0.1h topics) never leaves a
# sliver of a slot "open" due to binary float error, and never over-fills one.
_EPS = 1e-6

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# Accept common short forms in stored calendar/timetable data.
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


class SchedulerValidationError(Exception):
    """Raised for malformed scheduler input (invalid dates, times, etc.).

    The API layer maps this to a controlled 400/422 response. The message is
    safe to surface to the client (it never contains internal details).
    """


class ScheduleConflictError(Exception):
    """Raised when generated sessions clash with existing schedules.

    Carries a structured ``conflicts`` report that the API layer surfaces with
    HTTP 409 so nothing is silently overwritten.
    """

    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        super().__init__("Schedule conflict detected")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_date(value, field: str = "date") -> date:
    """Safely coerce a stored value into a ``datetime.date``.

    Accepts ``date``/``datetime`` objects (already-typed Mongo values) or
    ISO-ish strings (``YYYY-MM-DD``, optionally with a time component). Raises
    ``SchedulerValidationError`` for anything unparseable instead of letting a
    raw ``ValueError`` bubble up as a 500.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw:
            # Take the date portion if a full timestamp was stored.
            head = raw.replace("T", " ").split(" ")[0]
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(head, fmt).date()
                except ValueError:
                    continue
    raise SchedulerValidationError(
        f"Invalid {field}: '{value}' is not a recognizable date"
    )


def parse_time_to_minutes(value, field: str = "time") -> int:
    """Parse an ``HH:MM`` (optionally ``HH:MM:SS``) string into minutes."""
    if not isinstance(value, str):
        raise SchedulerValidationError(f"Invalid {field}: expected 'HH:MM' string")
    parts = value.strip().split(":")
    try:
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        raise SchedulerValidationError(
            f"Invalid {field}: '{value}' is not valid 'HH:MM' time"
        )
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise SchedulerValidationError(
            f"Invalid {field}: '{value}' is out of range"
        )
    return hours * 60 + minutes


def minutes_to_hhmm(total_minutes: int) -> str:
    total_minutes = int(round(total_minutes))
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def normalize_weekday(name) -> str:
    """Normalize a weekday label to canonical Title-case (e.g. ``Monday``)."""
    if not isinstance(name, str) or not name.strip():
        raise SchedulerValidationError(f"Invalid weekday: '{name}'")
    key = name.strip().lower()
    if key in _WEEKDAY_ALIASES:
        return _WEEKDAY_ALIASES[key]
    canonical = key.capitalize()
    if canonical in WEEKDAYS:
        return canonical
    raise SchedulerValidationError(f"Invalid weekday: '{name}'")


# ---------------------------------------------------------------------------
# Input extraction
# ---------------------------------------------------------------------------


def extract_topics(structured_plan: dict | None) -> list[dict]:
    """Flatten a structured lesson plan into an ordered list of teachable topics.

    Preserves unit order, then topic order within each unit (Phase 7). Each
    returned item carries the identifying metadata every session needs.

    Raises ``SchedulerValidationError`` if the structured plan is missing or has
    no usable units/topics (this is the backward-compatibility guard for old
    lesson plans that only have the flat ``lesson_plan`` text — Phase 14).
    """
    if not isinstance(structured_plan, dict):
        raise SchedulerValidationError(
            "Structured lesson plan required. Regenerate the lesson plan before scheduling."
        )

    units = structured_plan.get("units")
    if not isinstance(units, list) or not units:
        raise SchedulerValidationError(
            "Structured lesson plan required. Regenerate the lesson plan before scheduling."
        )

    topics: list[dict] = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        unit_number = unit.get("unit_number")
        unit_title = unit.get("unit_title", "")
        unit_topics = unit.get("topics") or []
        for order, topic in enumerate(unit_topics):
            if not isinstance(topic, dict):
                continue
            name = (topic.get("topic") or "").strip()
            if not name:
                continue
            try:
                hours = float(topic.get("estimated_hours", 1) or 0)
            except (TypeError, ValueError):
                hours = 0.0
            topics.append(
                {
                    "topic_id": topic.get("topic_id")
                    or f"U{unit_number}-T{order + 1}",
                    "topic": name,
                    "unit_number": unit_number,
                    "unit_title": unit_title,
                    "estimated_hours": hours,
                }
            )

    if not topics:
        raise SchedulerValidationError(
            "Structured lesson plan contains no schedulable topics. Regenerate the lesson plan."
        )
    return topics


def build_available_dates(
    semester_start,
    semester_end,
    working_days,
    holidays,
    internal_exams,
) -> list[date]:
    """Produce every valid teaching date in the semester window (Phases 3-4).

    A date is valid when its weekday is a configured working day and it is not a
    holiday or an internal-examination day. Weekends/non-working days, holidays
    and exam days are skipped.
    """
    start = parse_date(semester_start, "semester_start")
    end = parse_date(semester_end, "semester_end")
    if end < start:
        raise SchedulerValidationError(
            "Invalid calendar: semester_end is before semester_start"
        )

    if not isinstance(working_days, (list, tuple)) or not working_days:
        raise SchedulerValidationError("Invalid calendar: no working days configured")
    working = {normalize_weekday(day) for day in working_days}

    holiday_set = {parse_date(d, "holiday") for d in (holidays or [])}
    exam_set = {parse_date(d, "internal_exam") for d in (internal_exams or [])}

    available: list[date] = []
    current = start
    one_day = timedelta(days=1)
    while current <= end:
        weekday_name = WEEKDAYS[current.weekday()]
        if (
            weekday_name in working
            and current not in holiday_set
            and current not in exam_set
        ):
            available.append(current)
        current += one_day
    return available


def build_slots_by_weekday(timetable_schedule, target_subject: str = None) -> dict[str, list[dict]]:
    """Group timetable slots by weekday and validate their times (Phase 5).

    Returns ``{weekday: [{"start": start_minutes, "end": end_minutes, ...}, ...]}`` 
    with slots sorted by start time so allocation is deterministic.
    """
    if not isinstance(timetable_schedule, list) or not timetable_schedule:
        raise SchedulerValidationError("Invalid timetable: no slots configured")

    slots: dict[str, list[dict]] = {}
    for slot in timetable_schedule:
        if not isinstance(slot, dict):
            raise SchedulerValidationError("Invalid timetable: malformed slot")
            
        subject = slot.get("subject")
        if target_subject and subject:
            targets = {t.strip().lower() for t in target_subject.split(",") if t.strip()}
            subject_parts = {p.strip().lower() for p in subject.replace("/", ",").split(",")}
            if not targets.intersection(subject_parts):
                continue
                
        weekday = normalize_weekday(slot.get("day"))
        
        ps = slot.get("period_start")
        pe = slot.get("period_end")
        st = slot.get("start_time")
        et = slot.get("end_time")
        
        if ps is not None and pe is not None:
            # Pseudo-minutes for period-based slots: Period N = N * 60
            start = int(ps) * 60
            end = (int(pe) + 1) * 60
        else:
            start = parse_time_to_minutes(st, "start_time")
            end = parse_time_to_minutes(et, "end_time")
            
        if end <= start:
            raise SchedulerValidationError(
                "Invalid timetable: end_time must be after start_time"
            )
            
        slots.setdefault(weekday, []).append({
            "start": start,
            "end": end,
            "period_start": ps,
            "period_end": pe,
            "start_time": st,
            "end_time": et
        })

    for weekday in slots:
        slots[weekday].sort(key=lambda s: s["start"])
    return slots


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def allocate_sessions(
    topics: list[dict],
    available_dates: list[date],
    slots_by_weekday: dict[str, list[dict]],
) -> tuple[list[dict], list[dict]]:
    """Walk dates -> slots and pour topic hours into them in order (Phases 6-7).

    A single topic may span multiple sessions/days, and a single slot may hold
    the tail of one topic followed by the head of the next. Time is tracked in
    minutes for precision, so fractional ``estimated_hours`` are handled cleanly.

    Returns ``(sessions, unscheduled)`` where ``unscheduled`` lists topics (with
    remaining hours) that did not fit inside the semester window.
    """
    queue = [t for t in topics if t["estimated_hours"] and t["estimated_hours"] > 0]

    sessions: list[dict] = []
    if not queue:
        return sessions, []

    index = 0
    remaining = queue[index]["estimated_hours"] * 60  # minutes

    for day in available_dates:
        if index >= len(queue):
            break
        weekday_name = WEEKDAYS[day.weekday()]
        for slot in slots_by_weekday.get(weekday_name, []):
            cursor = slot["start"]
            slot_end = slot["end"]
            while cursor < slot_end and index < len(queue):
                block = min(slot_end - cursor, remaining)
                block = int(round(block))
                if block <= 0:
                    break
                topic = queue[index]
                
                session_ps = None
                session_pe = None
                session_st = None
                session_et = None
                
                if slot.get("period_start") is not None:
                    session_ps = cursor // 60
                    session_pe = (cursor + block - 1) // 60
                else:
                    session_st = minutes_to_hhmm(cursor)
                    session_et = minutes_to_hhmm(cursor + block)
                    
                sessions.append(
                    {
                        "topic_id": topic["topic_id"],
                        "topic": topic["topic"],
                        "unit_number": topic["unit_number"],
                        "unit_title": topic["unit_title"],
                        "date": day.isoformat(),
                        "day": weekday_name,
                        "start_time": session_st,
                        "end_time": session_et,
                        "period_start": session_ps,
                        "period_end": session_pe,
                        "duration_hours": round(block / 60, 2),
                        "status": "pending",
                    }
                )
                cursor += block
                remaining -= block
                if remaining <= 0:
                    index += 1
                    if index < len(queue):
                        remaining = queue[index]["estimated_hours"] * 60
            if index >= len(queue):
                break

    unscheduled: list[dict] = []
    if index < len(queue):
        # Current topic may be partially scheduled.
        current = queue[index]
        unscheduled.append(
            {
                "topic_id": current["topic_id"],
                "topic": current["topic"],
                "remaining_hours": round(remaining / 60, 2),
            }
        )
        for leftover in queue[index + 1 :]:
            unscheduled.append(
                {
                    "topic_id": leftover["topic_id"],
                    "topic": leftover["topic"],
                    "remaining_hours": round(leftover["estimated_hours"], 2),
                }
            )
    return sessions, unscheduled


# ---------------------------------------------------------------------------
# Conflict detection & workload
# ---------------------------------------------------------------------------


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def detect_conflicts(
    new_sessions: list[dict],
    existing_sessions: list[dict],
) -> list[dict]:
    """Report overlaps between new sessions and pre-existing ones (Phase 8).

    ``existing_sessions`` must already be scoped by the caller to the relevant
    entities (same faculty and/or same course). Each existing session should
    carry ``date``, ``start_time``, ``end_time`` and a ``reason``/label describing
    its source so the returned report is actionable. Nothing is overwritten here.
    """
    conflicts: list[dict] = []
    for new in new_sessions:
        new_start = parse_time_to_minutes(new["start_time"], "start_time")
        new_end = parse_time_to_minutes(new["end_time"], "end_time")
        for existing in existing_sessions:
            if new["date"] != existing.get("date"):
                continue
            ex_start = parse_time_to_minutes(existing["start_time"], "start_time")
            ex_end = parse_time_to_minutes(existing["end_time"], "end_time")
            if _overlaps(new_start, new_end, ex_start, ex_end):
                conflicts.append(
                    {
                        "date": new["date"],
                        "day": new["day"],
                        "new_slot": f"{new['start_time']}-{new['end_time']}",
                        "existing_slot": f"{existing['start_time']}-{existing['end_time']}",
                        "topic": new["topic"],
                        "reason": existing.get("reason", "Overlapping session"),
                    }
                )
    return conflicts


def calculate_total_hours(sessions: list[dict]) -> float:
    """Sum the teaching hours across generated sessions (Phase 9 workload)."""
    total = sum(session.get("duration_hours", 0) for session in sessions)
    return round(total, 2)


# ===========================================================================
# Task #5 — academic-calendar + period-based scheduling
#
# Everything below is additive. The legacy clock-time helpers above are left
# untouched so pre-existing behaviour (and their tests) keep working. The new
# engine is calendar-aware (blocked date ranges + special/swap timetable days)
# and period-aware (Hour 1..7, lunch never schedulable, multi-period lab
# blocks), while still supporting legacy clock-time timetables through the same
# allocator via a small "block" abstraction.
#
# The engine stays pure: the *service* reads Mongo, normalizes the calendar
# (holidays / exam ranges / vacation / blocked periods / special days) and the
# timetable, and hands plain Python data to these functions.
# ===========================================================================


def _coerce_date(value, field: str = "date") -> date:
    """Accept an already-typed ``date``/``datetime`` or parse a string."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_date(value, field)


class TeachableDay(tuple):
    """A backwards-compatible 2-tuple (date, weekday) that also stores day_order."""
    def __new__(cls, day_date, weekday, day_order):
        return super().__new__(cls, (day_date, weekday))
    def __init__(self, day_date, weekday, day_order):
        self.day_order = day_order

def build_teachable_days(
    calendar_model,
    semester_start,
    semester_end=None,
    working_days=None,
    blocked_dates=None,
    special_days=None,
) -> list[TeachableDay]:
    """Return every teachable day as ``(calendar_date, effective_weekday, effective_day_order)``.

    Delegates date resolution to ``calendar_resolver.resolve_date``, which acts as
    the single source of truth for holidays, special days, and day-order logic.
    """
    from datetime import date
    if isinstance(calendar_model, (str, date)):
        actual_start = calendar_model
        actual_end = semester_start
        actual_working = working_days or []
        if isinstance(semester_end, list):
            actual_working = semester_end
        calendar_model = {
            "working_days": actual_working,
            "holidays": [{"date": d.isoformat() if hasattr(d, "isoformat") else d} for d in (blocked_dates or [])],
            "special_days": special_days or []
        }
        semester_start = actual_start
        semester_end = actual_end
        
    from app.services.calendar_resolver import resolve_date

    start = _coerce_date(semester_start, "semester_start")
    end = _coerce_date(semester_end, "semester_end")
    if end < start:
        raise SchedulerValidationError(
            "Invalid calendar: semester_end is before semester_start"
        )

    teachable: list[tuple[date, str, int | None]] = []
    teachable: list[TeachableDay] = []
    current = start
    while current <= end:
        resolution = resolve_date(calendar_model, current)
        if resolution["is_working_day"]:
            teachable.append(TeachableDay(
                day_date=current, 
                weekday=resolution["effective_day"], 
                day_order=resolution["effective_day_order"]
            ))
        current += timedelta(days=1)
    if not teachable:
        raise SchedulerValidationError(
            "No valid working days found in the provided calendar between the start and end dates."
        )
    return teachable


def timetable_is_period_based(timetable_schedule) -> bool:
    """Return ``True`` when the timetable uses the new period model.

    A timetable is period-based when at least one slot carries both
    ``period_start`` and ``period_end``. Otherwise it is treated as a legacy
    clock-time timetable (Task #5 req. 12 — backward compatibility).
    """
    for slot in timetable_schedule or []:
        if not isinstance(slot, dict):
            continue
        if slot.get("period_start") is not None and slot.get("period_end") is not None:
            return True
    return False


def build_period_slots_by_weekday(
    timetable_schedule,
    target_subject: str = None,
) -> dict[str, list[tuple[int, int]]]:
    """Group period-based slots by weekday (Task #5 req. 4-5).

    Returns ``{weekday: [(period_start, period_end), ...]}`` sorted by
    ``period_start`` so allocation is deterministic. A single period is
    ``period_start == period_end``; a lab / multi-period block is
    ``period_start < period_end`` and is kept as ONE block. Legacy clock-only
    slots are skipped (they are handled by the clock path).
    """
    if not isinstance(timetable_schedule, list) or not timetable_schedule:
        raise SchedulerValidationError("Invalid timetable: no slots configured")

    slots: dict[str, list[tuple[int, int]]] = {}
    found = False
    for slot in timetable_schedule:
        if not isinstance(slot, dict):
            raise SchedulerValidationError("Invalid timetable: malformed slot")
        
        subject = slot.get("subject")
        if target_subject and subject:
            targets = {t.strip().lower() for t in target_subject.split(",") if t.strip()}
            subject_parts = {p.strip().lower() for p in subject.replace("/", ",").split(",")}
            
            # Also allow common exam/test slots through so they can be overridden by CIA ranges
            is_exam_slot = any(
                exam_term in subject.lower() 
                for exam_term in ["unit test", "cia", "exam", "test", "result"]
            )
            
            if not targets.intersection(subject_parts) and not is_exam_slot:
                continue

        p_start = slot.get("period_start")
        p_end = slot.get("period_end")
        if p_start is None or p_end is None:
            continue  # legacy clock-only slot; not part of the period grid
        try:
            p_start = int(p_start)
            p_end = int(p_end)
        except (TypeError, ValueError):
            raise SchedulerValidationError(
                "Invalid timetable: period_start/period_end must be integers"
            )
        if p_start < PERIOD_MIN or p_end > PERIOD_MAX or p_start > p_end:
            raise SchedulerValidationError(
                f"Invalid timetable: period range Hour {p_start}-{p_end} is out "
                f"of the valid {PERIOD_MIN}..{PERIOD_MAX} range"
            )
        weekday = normalize_weekday(slot.get("day"))
        day_order = slot.get("day_order")
        
        # Index by both weekday (e.g. "Monday") and day_order string (e.g. "Order:3")
        slots.setdefault(weekday, []).append((p_start, p_end))
        if day_order is not None:
            slots.setdefault(f"Order:{day_order}", []).append((p_start, p_end))
            
        found = True

    if not found:
        # Avoid crashing completely if subject filter causes 0 slots.
        pass

    for weekday in slots:
        slots[weekday].sort(key=lambda pair: pair[0])
    return slots


def expand_period(period_start: int, period_end: int) -> list[int]:
    return list(range(period_start, period_end + 1))

def reconstruct_blocks(hours: set[int]) -> list[tuple[int, int]]:
    if not hours:
        return []
    
    sorted_hours = sorted(hours)
    blocks = []
    
    start = sorted_hours[0]
    previous = sorted_hours[0]
    
    for hour in sorted_hours[1:]:
        if hour == previous + 1:
            previous = hour
            continue
            
        blocks.append((start, previous))
        start = hour
        previous = hour
        
    blocks.append((start, previous))
    return blocks

def build_period_blocks(
    teachable_days: list[TeachableDay],
    period_slots_by_weekday: dict[str, list[tuple[int, int]]],
    period_time_map: dict | None = None,
) -> list[dict]:
    """Expand teachable days into an ordered list of period teaching blocks.

    Each block covers exactly one timetable slot on one date.
    Prioritizes Day Order matches additively with the effective weekday.
    """
    blocks: list[dict] = []
    for day in teachable_days:
        day_date = day[0]
        effective_weekday = day[1]
        day_order = day[2] if len(day) >= 3 else getattr(day, "day_order", None)
        
        # 1. Base slot matching logic via physical hour units
        hours = set()
        
        # Regular timetable only (Special Day Order processing has been removed per user request)
        regular_slots = period_slots_by_weekday.get(effective_weekday, [])
        for p_start, p_end in regular_slots:
            hours.update(expand_period(p_start, p_end))
            
            
        # Domain Rule: Saturday must never generate hours 5-7.
        if WEEKDAYS[day_date.weekday()] == "Saturday":
            hours &= {1, 2, 3, 4}
            
        reconstructed = reconstruct_blocks(hours)
        
        for p_start, p_end in reconstructed:
            blocks.append(
                {
                    "kind": "period",
                    "date": day_date,
                    "day": WEEKDAYS[day_date.weekday()],
                    "timetable_day": effective_weekday,
                    "period_start": p_start,
                    "period_end": p_end,
                    "capacity": float(p_end - p_start + 1),
                    "period_time_map": period_time_map,
                    "session_type": ScheduleType.CLASS.value,
                }
            )
    return blocks


def apply_exam_overrides(
    blocks: list[dict],
    exam_configs: list[dict]
) -> list[dict]:
    """Reserve teaching capacity during exams (e.g., Periods 1 and 2)."""
    if not exam_configs:
        return blocks
        
    # Map dates to their exam configurations
    exam_dates = {}
    for config in exam_configs:
        start = parse_date(config["start_date"], "start_date")
        end = parse_date(config["end_date"], "end_date")
        # Default to all weekdays if not specified
        exam_days = config.get("exam_days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])
        duration = int(config.get("duration", 2))
        
        current = start
        while current <= end:
            # We take the maximum duration if multiple configs overlap on the same day
            if current not in exam_dates:
                exam_dates[current] = {"exam_days": set(exam_days), "duration": duration}
            else:
                exam_dates[current]["exam_days"].update(exam_days)
                exam_dates[current]["duration"] = max(exam_dates[current]["duration"], duration)
            current += timedelta(days=1)
            
    processed_blocks = []
    for block in blocks:
        if block["kind"] != "period" or block["date"] not in exam_dates:
            processed_blocks.append(block)
            continue
            
        config = exam_dates[block["date"]]
        
        if block["day"] not in config["exam_days"]:
            processed_blocks.append(block)
            continue
            
        p_start = block["period_start"]
        p_end = block["period_end"]
        
        exam_start = 1
        exam_end = config["duration"]
        
        # Expand block into physical hours
        hours = set(expand_period(p_start, p_end))
        
        # Expand exam into physical hours
        exam_hours = set(expand_period(exam_start, exam_end))
        
        # Set subtraction strictly removes only the overlapping hours
        remaining_hours = hours - exam_hours
        
        # Reconstruct contiguous blocks from remaining hours
        reconstructed = reconstruct_blocks(remaining_hours)
        
        for r_start, r_end in reconstructed:
            new_block = block.copy()
            new_block["period_start"] = r_start
            new_block["period_end"] = r_end
            new_block["capacity"] = float(r_end - r_start + 1)
            processed_blocks.append(new_block)
            
    return processed_blocks


def build_clock_blocks(
    teachable_days: list[tuple[date, str, int | None]],
    clock_slots_by_weekday: dict[str, list[dict]],
) -> list[dict]:
    """Expand teachable days into ordered legacy clock-time blocks.

    ``clock_slots_by_weekday`` is the ``{weekday: [(start_min, end_min), ...]}``
    mapping produced by :func:`build_slots_by_weekday`. Capacity is measured in
    hours so a topic's ``estimated_hours`` pours in identically to the period
    path.
    """
    blocks: list[dict] = []
    for day in teachable_days:
        day_date = day[0]
        effective_weekday = day[1]
        for slot in clock_slots_by_weekday.get(effective_weekday, []):
            start_min = slot["start"]
            end_min = slot["end"]
            blocks.append(
                {
                    "kind": "clock",
                    "date": day_date,
                    "day": WEEKDAYS[day_date.weekday()],
                    "timetable_day": effective_weekday,
                    "start_minutes": start_min,
                    "end_minutes": end_min,
                    "capacity": (end_min - start_min) / 60.0,
                }
            )
    return blocks


def _period_block_fields(block: dict, cursor: float, take: float) -> dict:
    """Compute the ``period_start``/``period_end`` (and optional clock times)
    for the chunk ``[cursor, cursor + take)`` inside a period block.

    Period numbers stay canonical integers within the block's own range, so no
    invalid period durations are ever invented. For whole-period allocations
    (the common case) the mapping is exact; fractional topics simply share the
    period they straddle.
    """
    base = block["period_start"]
    start_period = base + int(math.floor(cursor + _EPS))
    end_period = base + int(math.ceil(cursor + take - _EPS)) - 1
    if end_period < start_period:
        end_period = start_period
    start_period = max(start_period, block["period_start"])
    end_period = min(end_period, block["period_end"])

    fields = {"period_start": start_period, "period_end": end_period}

    time_map = block.get("period_time_map")
    if time_map:
        start_times = time_map.get(start_period)
        end_times = time_map.get(end_period)
        if (
            start_times
            and end_times
            and start_times.get("start_time")
            and end_times.get("end_time")
        ):
            # Real clock times only when they have been configured; otherwise
            # period numbers remain the canonical representation (Task #5 req.6).
            fields["start_time"] = start_times["start_time"]
            fields["end_time"] = end_times["end_time"]
    return fields


def _clock_block_fields(block: dict, cursor: float, take: float) -> dict:
    start_min = block["start_minutes"] + cursor * 60
    end_min = start_min + take * 60
    return {
        "start_time": minutes_to_hhmm(start_min),
        "end_time": minutes_to_hhmm(end_min),
    }


def allocate_blocks(
    topics: list[dict],
    blocks: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Pour ordered topic hours into ordered teaching blocks (Task #5 req.10).

    Works for both period and clock blocks. Preserves the deterministic unit ->
    topic order from ``extract_topics``: a topic may span multiple blocks/dates,
    and a single block may hold the tail of one topic followed by the head of
    the next. Lunch, blocked dates and non-working days are already absent from
    ``blocks``, so allocation can never land on them.

    Returns ``(sessions, unscheduled)`` where ``unscheduled`` lists topics (with
    remaining hours) that did not fit before the semester ended.
    """
    queue = [t for t in topics if t.get("estimated_hours") and t["estimated_hours"] > 0]

    sessions: list[dict] = []
    if not queue:
        return sessions, []

    # Per-topic occurrence counter used to mint a STABLE, position-independent
    # ``session_id`` (Task #6 req. 2). A topic that spans several blocks yields
    # ``<topic_id>-s1``, ``<topic_id>-s2`` … in deterministic allocation order.
    # Because the id derives from the topic identity + its occurrence (never the
    # array index), it regenerates identically whenever the lesson plan's topic
    # and its hour split are unchanged — which is exactly what makes safe
    # carry-forward on regeneration possible (req. 11).
    seq_by_topic: dict = {}

    index = 0
    remaining = float(queue[index]["estimated_hours"])  # hours

    for block in blocks:
        if block.get("session_type") == ScheduleType.EXAM.value:
            session = {
                "session_id": f"exam-{block['date']}-p{block.get('period_start')}",
                "topic_id": "exam",
                "topic": "CIA Examination",
                "unit_number": "-",
                "unit_title": "-",
                "date": block["date"].isoformat(),
                "day": block["day"],
                "timetable_day": block["timetable_day"],
                "duration_hours": round(block["capacity"], 2),
                "status": "scheduled",
            }
            if block["kind"] == "period":
                session.update(_period_block_fields(block, 0, block["capacity"]))
            else:
                session.update(_clock_block_fields(block, 0, block["capacity"]))
            sessions.append(session)
            continue

        if index >= len(queue):
            break
            
        capacity = float(block["capacity"])
        cursor = 0.0
        while cursor < capacity - _EPS and index < len(queue):
            take = min(capacity - cursor, remaining)
            if take <= _EPS:
                break
            topic = queue[index]
            occurrence = seq_by_topic.get(topic["topic_id"], 0) + 1
            seq_by_topic[topic["topic_id"]] = occurrence
            session = {
                "session_id": f"{topic['topic_id']}-s{occurrence}",
                "topic_id": topic["topic_id"],
                "topic": topic["topic"],
                "unit_number": topic["unit_number"],
                "unit_title": topic["unit_title"],
                "date": block["date"].isoformat(),
                "day": block["day"],
                "timetable_day": block["timetable_day"],
                "duration_hours": round(take, 2),
                "status": "pending",
            }
            if block["kind"] == "period":
                session.update(_period_block_fields(block, cursor, take))
            else:
                session.update(_clock_block_fields(block, cursor, take))
            sessions.append(session)

            cursor += take
            remaining -= take
            if remaining <= _EPS:
                index += 1
                if index < len(queue):
                    remaining = float(queue[index]["estimated_hours"])

    unscheduled: list[dict] = []
    if index < len(queue):
        current = queue[index]
        unscheduled.append(
            {
                "topic_id": current["topic_id"],
                "topic": current["topic"],
                "unit_number": current["unit_number"],
                "remaining_hours": round(remaining, 2),
            }
        )
        for leftover in queue[index + 1 :]:
            unscheduled.append(
                {
                    "topic_id": leftover["topic_id"],
                    "topic": leftover["topic"],
                    "unit_number": leftover["unit_number"],
                    "remaining_hours": round(float(leftover["estimated_hours"]), 2),
                }
            )
    return sessions, unscheduled


def detect_session_conflicts(
    new_sessions: list[dict],
    existing_sessions: list[dict],
) -> list[dict]:
    """Report clashes on the SAME calendar date (Task #5 req. 8).

    Compares the *effective* timetable period (period-based) or clock time
    (legacy) between the new sessions and pre-existing ones. ``existing_sessions``
    must already be scoped to the relevant faculty by the caller. Period vs
    period compares period ranges; clock vs clock compares times; a period
    session and a clock session are treated as non-comparable (a faculty's
    timetables are consistently one style) and skipped rather than guessed.
    """
    conflicts: list[dict] = []
    for new in new_sessions:
        new_date = new.get("date")
        for existing in existing_sessions:
            if new_date != existing.get("date"):
                continue

            new_has_period = new.get("period_start") is not None
            ex_has_period = existing.get("period_start") is not None

            overlap = False
            new_slot = existing_slot = ""
            if new_has_period and ex_has_period:
                overlap = periods_overlap(
                    new["period_start"],
                    new["period_end"],
                    existing["period_start"],
                    existing["period_end"],
                )
                new_slot = f"Hour {new['period_start']}-{new['period_end']}"
                existing_slot = (
                    f"Hour {existing['period_start']}-{existing['period_end']}"
                )
            elif new.get("start_time") and existing.get("start_time"):
                new_start = parse_time_to_minutes(new["start_time"], "start_time")
                new_end = parse_time_to_minutes(new["end_time"], "end_time")
                ex_start = parse_time_to_minutes(existing["start_time"], "start_time")
                ex_end = parse_time_to_minutes(existing["end_time"], "end_time")
                overlap = _overlaps(new_start, new_end, ex_start, ex_end)
                new_slot = f"{new['start_time']}-{new['end_time']}"
                existing_slot = f"{existing['start_time']}-{existing['end_time']}"
            else:
                continue

            if overlap:
                conflicts.append(
                    {
                        "date": new_date,
                        "day": new.get("day"),
                        "timetable_day": new.get("timetable_day"),
                        "new_slot": new_slot,
                        "existing_slot": existing_slot,
                        "topic": new.get("topic"),
                        "reason": existing.get("reason", "Overlapping session"),
                    }
                )
    return conflicts
