"""Pure, deterministic lesson-scheduling engine.

This module contains no database or network access. It takes plain Python
data and produces conflict-free, day-wise lesson sessions.

The scheduler supports:
- Legacy clock-time timetables
- Period-based timetables
- Academic calendar blocked dates
- Special/swap timetable days
- Multi-period timetable blocks
- Existing-session conflict detection

All scheduling decisions are deterministic.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from app.utils.timetable_periods import (
    PERIOD_MAX,
    PERIOD_MIN,
    periods_overlap,
)

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
    """Raised for malformed scheduler input."""

    pass


class ScheduleConflictError(Exception):
    """Raised when generated sessions clash with existing schedules."""

    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        super().__init__("Schedule conflict detected")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_date(value, field: str = "date") -> date:
    """Safely coerce a stored value into a datetime.date."""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        raw = value.strip()

        if raw:
            head = raw.replace("T", " ").split(" ")[0]

            for fmt in (
                "%Y-%m-%d",
                "%d-%m-%Y",
                "%d/%m/%Y",
                "%Y/%m/%d",
            ):
                try:
                    return datetime.strptime(head, fmt).date()
                except ValueError:
                    continue

    raise SchedulerValidationError(
        f"Invalid {field}: '{value}' is not a recognizable date"
    )


def parse_time_to_minutes(value, field: str = "time") -> int:
    """Parse HH:MM or HH:MM:SS into minutes."""

    if not isinstance(value, str):
        raise SchedulerValidationError(
            f"Invalid {field}: expected 'HH:MM' string"
        )

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
    """Normalize weekday labels."""

    if not isinstance(name, str) or not name.strip():
        raise SchedulerValidationError(f"Invalid weekday: '{name}'")

    key = name.strip().lower()

    if key in _WEEKDAY_ALIASES:
        return _WEEKDAY_ALIASES[key]

    canonical = key.capitalize()

    if canonical in WEEKDAYS:
        return canonical

    raise SchedulerValidationError(
        f"Invalid weekday: '{name}'"
    )


# ---------------------------------------------------------------------------
# Input extraction
# ---------------------------------------------------------------------------


def extract_topics(structured_plan: dict | None) -> list[dict]:
    """Flatten a structured lesson plan into ordered topics."""

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
                hours = float(
                    topic.get("estimated_hours", 1) or 0
                )
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
            "Structured lesson plan contains no schedulable topics. "
            "Regenerate the lesson plan."
        )

    return topics


# ---------------------------------------------------------------------------
# Legacy calendar helpers
# ---------------------------------------------------------------------------


def build_available_dates(
    semester_start,
    semester_end,
    working_days,
    holidays,
    internal_exams,
) -> list[date]:

    start = parse_date(
        semester_start,
        "semester_start",
    )

    end = parse_date(
        semester_end,
        "semester_end",
    )

    if end < start:
        raise SchedulerValidationError(
            "Invalid calendar: semester_end is before semester_start"
        )

    if not isinstance(
        working_days,
        (list, tuple),
    ) or not working_days:
        raise SchedulerValidationError(
            "Invalid calendar: no working days configured"
        )

    working = {
        normalize_weekday(day)
        for day in working_days
    }

    holiday_set = {
        parse_date(d, "holiday")
        for d in (holidays or [])
    }

    exam_set = {
        parse_date(d, "internal_exam")
        for d in (internal_exams or [])
    }

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


# ---------------------------------------------------------------------------
# Legacy clock timetable
# ---------------------------------------------------------------------------


def build_slots_by_weekday(
    timetable_schedule,
) -> dict[str, list[tuple[int, int]]]:

    if not isinstance(
        timetable_schedule,
        list,
    ) or not timetable_schedule:
        raise SchedulerValidationError(
            "Invalid timetable: no slots configured"
        )

    slots: dict[str, list[tuple[int, int]]] = {}

    for slot in timetable_schedule:

        if not isinstance(slot, dict):
            raise SchedulerValidationError(
                "Invalid timetable: malformed slot"
            )

        weekday = normalize_weekday(
            slot.get("day")
        )

        start = parse_time_to_minutes(
            slot.get("start_time"),
            "start_time",
        )

        end = parse_time_to_minutes(
            slot.get("end_time"),
            "end_time",
        )

        if end <= start:
            raise SchedulerValidationError(
                "Invalid timetable: end_time must be after start_time"
            )

        slots.setdefault(
            weekday,
            [],
        ).append(
            (start, end)
        )

    for weekday in slots:
        slots[weekday].sort(
            key=lambda pair: pair[0]
        )

    return slots


# ---------------------------------------------------------------------------
# Legacy allocator
# ---------------------------------------------------------------------------


def allocate_sessions(
    topics: list[dict],
    available_dates: list[date],
    slots_by_weekday: dict[str, list[tuple[int, int]]],
) -> tuple[list[dict], list[dict]]:

    queue = [
        t
        for t in topics
        if t["estimated_hours"]
        and t["estimated_hours"] > 0
    ]

    sessions: list[dict] = []

    if not queue:
        return sessions, []

    index = 0

    remaining = (
        queue[index]["estimated_hours"] * 60
    )

    for day in available_dates:

        if index >= len(queue):
            break

        weekday_name = WEEKDAYS[
            day.weekday()
        ]

        for (
            slot_start,
            slot_end,
        ) in slots_by_weekday.get(
            weekday_name,
            [],
        ):

            cursor = slot_start

            while (
                cursor < slot_end
                and index < len(queue)
            ):

                block = min(
                    slot_end - cursor,
                    remaining,
                )

                block = int(round(block))

                if block <= 0:
                    break

                topic = queue[index]

                sessions.append(
                    {
                        "topic_id": topic["topic_id"],
                        "topic": topic["topic"],
                        "unit_number": topic["unit_number"],
                        "unit_title": topic["unit_title"],
                        "date": day.isoformat(),
                        "day": weekday_name,
                        "start_time": minutes_to_hhmm(cursor),
                        "end_time": minutes_to_hhmm(
                            cursor + block
                        ),
                        "duration_hours": round(
                            block / 60,
                            2,
                        ),
                        "status": "pending",
                    }
                )

                cursor += block
                remaining -= block

                if remaining <= _EPS:

                    index += 1

                    if index < len(queue):
                        remaining = (
                            queue[index]["estimated_hours"]
                            * 60
                        )

            if index >= len(queue):
                break

    unscheduled: list[dict] = []

    if index < len(queue):

        current = queue[index]

        unscheduled.append(
            {
                "topic_id": current["topic_id"],
                "topic": current["topic"],
                "remaining_hours": round(
                    remaining / 60,
                    2,
                ),
            }
        )

        for leftover in queue[index + 1:]:

            unscheduled.append(
                {
                    "topic_id": leftover["topic_id"],
                    "topic": leftover["topic"],
                    "remaining_hours": round(
                        leftover["estimated_hours"],
                        2,
                    ),
                }
            )

    return sessions, unscheduled


# ---------------------------------------------------------------------------
# Legacy conflict detection
# ---------------------------------------------------------------------------


def _overlaps(
    start_a: int,
    end_a: int,
    start_b: int,
    end_b: int,
) -> bool:

    return (
        start_a < end_b
        and start_b < end_a
    )


def detect_conflicts(
    new_sessions: list[dict],
    existing_sessions: list[dict],
) -> list[dict]:

    conflicts: list[dict] = []

    for new in new_sessions:

        new_start = parse_time_to_minutes(
            new["start_time"],
            "start_time",
        )

        new_end = parse_time_to_minutes(
            new["end_time"],
            "end_time",
        )

        for existing in existing_sessions:

            if new["date"] != existing.get("date"):
                continue

            ex_start = parse_time_to_minutes(
                existing["start_time"],
                "start_time",
            )

            ex_end = parse_time_to_minutes(
                existing["end_time"],
                "end_time",
            )

            if _overlaps(
                new_start,
                new_end,
                ex_start,
                ex_end,
            ):

                conflicts.append(
                    {
                        "date": new["date"],
                        "day": new["day"],
                        "new_slot": (
                            f"{new['start_time']}-"
                            f"{new['end_time']}"
                        ),
                        "existing_slot": (
                            f"{existing['start_time']}-"
                            f"{existing['end_time']}"
                        ),
                        "topic": new["topic"],
                        "reason": existing.get(
                            "reason",
                            "Overlapping session",
                        ),
                    }
                )

    return conflicts


def calculate_total_hours(
    sessions: list[dict],
) -> float:

    total = sum(
        session.get(
            "duration_hours",
            0,
        )
        for session in sessions
    )

    return round(total, 2)


# ===========================================================================
# Academic calendar + period-based scheduling
# ===========================================================================


def _coerce_date(
    value,
    field: str = "date",
) -> date:

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return parse_date(
        value,
        field,
    )


def build_teachable_days(
    semester_start,
    semester_end,
    working_days,
    blocked_dates=None,
    special_days=None,
) -> list[tuple[date, str]]:

    start = _coerce_date(
        semester_start,
        "semester_start",
    )

    end = _coerce_date(
        semester_end,
        "semester_end",
    )

    if end < start:
        raise SchedulerValidationError(
            "Invalid calendar: semester_end is before semester_start"
        )

    if not isinstance(
        working_days,
        (list, tuple, set),
    ) or not working_days:

        raise SchedulerValidationError(
            "Invalid calendar: no working days configured"
        )

    working = {
        normalize_weekday(day)
        for day in working_days
    }

    blocked_set: set[date] = {
        _coerce_date(
            d,
            "blocked_date",
        )
        for d in (blocked_dates or [])
    }

    special_map: dict[date, str] = {}

    for entry in special_days or []:

        if not isinstance(entry, dict):
            raise SchedulerValidationError(
                "Invalid special day configuration"
            )

        entry_date = _coerce_date(
            entry.get("date"),
            "special_day",
        )

        timetable_day = normalize_weekday(
            entry.get("timetable_day")
        )

        special_map[entry_date] = timetable_day

    teachable: list[tuple[date, str]] = []

    current = start
    one_day = timedelta(days=1)

    while current <= end:

        if current not in blocked_set:

            effective_weekday = special_map.get(
                current,
                WEEKDAYS[current.weekday()],
            )

            if effective_weekday in working:
                teachable.append(
                    (
                        current,
                        effective_weekday,
                    )
                )

        current += one_day

    return teachable


# ---------------------------------------------------------------------------
# Period timetable helpers
# ---------------------------------------------------------------------------


def timetable_is_period_based(
    timetable_schedule,
) -> bool:

    for slot in timetable_schedule or []:

        if not isinstance(slot, dict):
            continue

        if (
            slot.get("period_start") is not None
            and slot.get("period_end") is not None
        ):
            return True

    return False


def build_period_slots_by_weekday(
    timetable_schedule,
) -> dict[str, list[tuple[int, int]]]:

    if not isinstance(
        timetable_schedule,
        list,
    ) or not timetable_schedule:

        raise SchedulerValidationError(
            "Invalid timetable: no slots configured"
        )

    slots: dict[
        str,
        list[tuple[int, int]]
    ] = {}

    found = False

    for slot in timetable_schedule:

        if not isinstance(slot, dict):
            raise SchedulerValidationError(
                "Invalid timetable: malformed slot"
            )

        p_start = slot.get(
            "period_start"
        )

        p_end = slot.get(
            "period_end"
        )

        if p_start is None or p_end is None:
            continue

        try:
            p_start = int(p_start)
            p_end = int(p_end)

        except (TypeError, ValueError):

            raise SchedulerValidationError(
                "Invalid timetable: period_start/period_end "
                "must be integers"
            )

        if (
            p_start < PERIOD_MIN
            or p_end > PERIOD_MAX
            or p_start > p_end
        ):

            raise SchedulerValidationError(
                f"Invalid timetable: period range "
                f"Hour {p_start}-{p_end} is out of the "
                f"valid {PERIOD_MIN}..{PERIOD_MAX} range"
            )

        weekday = normalize_weekday(
            slot.get("day")
        )

        slots.setdefault(
            weekday,
            [],
        ).append(
            (p_start, p_end)
        )

        found = True

    if not found:

        raise SchedulerValidationError(
            "Invalid timetable: no period-based slots configured"
        )

    for weekday in slots:

        slots[weekday].sort(
            key=lambda pair: pair[0]
        )

        previous_end = PERIOD_MIN - 1

        for p_start, p_end in slots[weekday]:

            if p_start <= previous_end:

                raise SchedulerValidationError(
                    f"Invalid timetable: overlapping "
                    f"period blocks on {weekday}"
                )

            previous_end = p_end

    return slots


def build_period_time_map_by_weekday(
    timetable_schedule,
) -> dict[str, dict[int, dict[str, str]]]:

    if not isinstance(
        timetable_schedule,
        list,
    ) or not timetable_schedule:

        raise SchedulerValidationError(
            "Invalid timetable: no slots configured"
        )

    time_map: dict[
        str,
        dict[int, dict[str, str]]
    ] = {}

    for slot in timetable_schedule:

        if not isinstance(slot, dict):
            raise SchedulerValidationError(
                "Invalid timetable: malformed slot"
            )

        p_start = slot.get(
            "period_start"
        )

        p_end = slot.get(
            "period_end"
        )

        if p_start is None or p_end is None:
            continue

        try:
            p_start = int(p_start)
            p_end = int(p_end)

        except (TypeError, ValueError):

            raise SchedulerValidationError(
                "Invalid timetable: period_start/period_end "
                "must be integers"
            )

        weekday = normalize_weekday(
            slot.get("day")
        )

        start_time = slot.get(
            "start_time"
        )

        end_time = slot.get(
            "end_time"
        )

        if start_time and end_time:

            parse_time_to_minutes(
                start_time,
                "start_time",
            )

            parse_time_to_minutes(
                end_time,
                "end_time",
            )

            time_map.setdefault(
                weekday,
                {}
            )

            for period in range(
                p_start,
                p_end + 1,
            ):

                time_map[weekday][period] = {
                    "start_time": start_time,
                    "end_time": end_time,
                }

    return time_map


# ---------------------------------------------------------------------------
# Block construction
# ---------------------------------------------------------------------------


def build_period_blocks(
    teachable_days: list[
        tuple[date, str]
    ],
    period_slots_by_weekday: dict[
        str,
        list[tuple[int, int]]
    ],
    period_time_map: dict | None = None,
) -> list[dict]:

    blocks: list[dict] = []

    for (
        day_date,
        effective_weekday,
    ) in teachable_days:

        for (
            p_start,
            p_end,
        ) in period_slots_by_weekday.get(
            effective_weekday,
            [],
        ):

            blocks.append(
                {
                    "kind": "period",
                    "date": day_date,
                    "day": WEEKDAYS[
                        day_date.weekday()
                    ],
                    "timetable_day": effective_weekday,
                    "period_start": p_start,
                    "period_end": p_end,
                    "capacity": float(
                        p_end - p_start + 1
                    ),
                    "period_time_map": (
                        period_time_map.get(
                            effective_weekday,
                            {},
                        )
                        if period_time_map
                        else {}
                    ),
                }
            )

    return blocks


def build_clock_blocks(
    teachable_days: list[
        tuple[date, str]
    ],
    clock_slots_by_weekday: dict[
        str,
        list[tuple[int, int]]
    ],
) -> list[dict]:

    blocks: list[dict] = []

    for (
        day_date,
        effective_weekday,
    ) in teachable_days:

        for (
            start_min,
            end_min,
        ) in clock_slots_by_weekday.get(
            effective_weekday,
            [],
        ):

            blocks.append(
                {
                    "kind": "clock",
                    "date": day_date,
                    "day": WEEKDAYS[
                        day_date.weekday()
                    ],
                    "timetable_day": effective_weekday,
                    "start_minutes": start_min,
                    "end_minutes": end_min,
                    "capacity": (
                        end_min - start_min
                    ) / 60.0,
                }
            )

    return blocks


# ---------------------------------------------------------------------------
# Session field builders
# ---------------------------------------------------------------------------


def _period_block_fields(
    block: dict,
    cursor: float,
    take: float,
) -> dict:

    base = block["period_start"]

    start_period = (
        base
        + int(
            math.floor(
                cursor + _EPS
            )
        )
    )

    end_period = (
        base
        + int(
            math.ceil(
                cursor
                + take
                - _EPS
            )
        )
        - 1
    )

    if end_period < start_period:
        end_period = start_period

    start_period = max(
        start_period,
        block["period_start"],
    )

    end_period = min(
        end_period,
        block["period_end"],
    )

    fields = {
        "period_start": start_period,
        "period_end": end_period,
    }

    time_map = block.get(
        "period_time_map"
    )

    if time_map:

        start_times = time_map.get(
            start_period
        )

        end_times = time_map.get(
            end_period
        )

        if (
            start_times
            and end_times
            and start_times.get(
                "start_time"
            )
            and end_times.get(
                "end_time"
            )
        ):

            fields["start_time"] = (
                start_times["start_time"]
            )

            fields["end_time"] = (
                end_times["end_time"]
            )

    return fields


def _clock_block_fields(
    block: dict,
    cursor: float,
    take: float,
) -> dict:

    start_min = (
        block["start_minutes"]
        + cursor * 60
    )

    end_min = (
        start_min
        + take * 60
    )

    return {
        "start_time": minutes_to_hhmm(
            start_min
        ),
        "end_time": minutes_to_hhmm(
            end_min
        ),
    }


# ---------------------------------------------------------------------------
# Main block allocator
# ---------------------------------------------------------------------------


def allocate_blocks(
    topics: list[dict],
    blocks: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Allocate lesson topics to available teaching blocks.

    Period-based scheduling:
    - Topics are sequential.
    - Required periods are calculated using ceil().
    - A timetable block is indivisible.
    - A topic can consume a block only when the topic has enough remaining
      periods for that block.
    - Multi-period blocks are therefore never partially consumed.

    Legacy clock scheduling:
    - Existing fractional-hour behavior is preserved.
    """

    queue = [
        t
        for t in topics
        if t.get("estimated_hours")
        and float(
            t["estimated_hours"]
        ) > 0
    ]

    sessions: list[dict] = []

    if not queue:
        return sessions, []

    seq_by_topic: dict[str, int] = {}

    index = 0

    est_hours = float(
        queue[index]["estimated_hours"]
    )

    remaining_periods = max(
        1,
        math.ceil(
            est_hours - _EPS
        ),
    )

    scheduled_periods = 0

    remaining_clock_hours = est_hours

    is_period_mode = any(
        block.get("kind") == "period"
        for block in blocks
    ) if blocks else False

    for block in blocks:

        if index >= len(queue):
            break

        capacity = float(
            block["capacity"]
        )

        # ---------------------------------------------------------------
        # Period-based timetable
        # ---------------------------------------------------------------

        if block["kind"] == "period":

            block_periods = int(
                capacity
            )

            # A block is indivisible.
            # Do not put a 1-hour topic into a 2-hour lab block.
            if remaining_periods < block_periods:
                continue

            take_periods = block_periods

            topic = queue[index]

            occurrence = (
                seq_by_topic.get(
                    topic["topic_id"],
                    0,
                )
                + 1
            )

            seq_by_topic[
                topic["topic_id"]
            ] = occurrence

            session = {
                "session_id": (
                    f"{topic['topic_id']}"
                    f"-s{occurrence}"
                ),
                "topic_id": topic["topic_id"],
                "topic": topic["topic"],
                "unit_number": topic["unit_number"],
                "unit_title": topic["unit_title"],
                "date": block[
                    "date"
                ].isoformat(),
                "day": block["day"],
                "timetable_day": block[
                    "timetable_day"
                ],
                "duration_hours": round(
                    float(take_periods),
                    2,
                ),
                "status": "pending",
            }

            session.update(
                _period_block_fields(
                    block,
                    0.0,
                    float(take_periods),
                )
            )

            sessions.append(
                session
            )

            remaining_periods -= (
                take_periods
            )

            scheduled_periods += (
                take_periods
            )

            if remaining_periods <= 0:

                index += 1

                if index < len(queue):

                    est_hours = float(
                        queue[index][
                            "estimated_hours"
                        ]
                    )

                    remaining_periods = max(
                        1,
                        math.ceil(
                            est_hours - _EPS
                        ),
                    )

                    scheduled_periods = 0

                    remaining_clock_hours = (
                        est_hours
                    )

        # ---------------------------------------------------------------
        # Legacy clock-based timetable
        # ---------------------------------------------------------------

        else:

            cursor = 0.0

            while (
                cursor
                < capacity - _EPS
                and index < len(queue)
            ):

                take = min(
                    capacity - cursor,
                    remaining_clock_hours,
                )

                if take <= _EPS:
                    break

                topic = queue[index]

                occurrence = (
                    seq_by_topic.get(
                        topic["topic_id"],
                        0,
                    )
                    + 1
                )

                seq_by_topic[
                    topic["topic_id"]
                ] = occurrence

                session = {
                    "session_id": (
                        f"{topic['topic_id']}"
                        f"-s{occurrence}"
                    ),
                    "topic_id": topic["topic_id"],
                    "topic": topic["topic"],
                    "unit_number": topic["unit_number"],
                    "unit_title": topic["unit_title"],
                    "date": block[
                        "date"
                    ].isoformat(),
                    "day": block["day"],
                    "timetable_day": block[
                        "timetable_day"
                    ],
                    "duration_hours": round(
                        take,
                        2,
                    ),
                    "status": "pending",
                }

                session.update(
                    _clock_block_fields(
                        block,
                        cursor,
                        take,
                    )
                )

                sessions.append(
                    session
                )

                cursor += take

                remaining_clock_hours -= (
                    take
                )

                if (
                    remaining_clock_hours
                    <= _EPS
                ):

                    index += 1

                    if index < len(queue):

                        est_hours = float(
                            queue[index][
                                "estimated_hours"
                            ]
                        )

                        remaining_periods = max(
                            1,
                            math.ceil(
                                est_hours
                                - _EPS
                            ),
                        )

                        scheduled_periods = 0

                        remaining_clock_hours = (
                            est_hours
                        )

    # ------------------------------------------------------------------
    # Unscheduled topics
    # ------------------------------------------------------------------

    unscheduled: list[dict] = []

    if index < len(queue):

        current = queue[index]

        est_hours = float(
            current["estimated_hours"]
        )

        if is_period_mode:

            # scheduled_periods represents actual periods consumed for
            # the current topic.
            shortage = max(
                0.0,
                est_hours
                - float(
                    scheduled_periods
                ),
            )

            # If the topic was never schedulable because the remaining
            # requirement was smaller than an available multi-period block,
            # preserve its original estimated hours as unscheduled.
            if scheduled_periods == 0:
                shortage = est_hours

        else:

            shortage = max(
                0.0,
                remaining_clock_hours,
            )

        unscheduled.append(
            {
                "topic_id": current[
                    "topic_id"
                ],
                "topic": current["topic"],
                "unit_number": current[
                    "unit_number"
                ],
                "remaining_hours": round(
                    shortage,
                    2,
                ),
            }
        )

        for leftover in queue[
            index + 1:
        ]:

            unscheduled.append(
                {
                    "topic_id": leftover[
                        "topic_id"
                    ],
                    "topic": leftover[
                        "topic"
                    ],
                    "unit_number": leftover[
                        "unit_number"
                    ],
                    "remaining_hours": round(
                        float(
                            leftover[
                                "estimated_hours"
                            ]
                        ),
                        2,
                    ),
                }
            )

    return sessions, unscheduled


# ---------------------------------------------------------------------------
# Period / clock conflict detection
# ---------------------------------------------------------------------------


def detect_session_conflicts(
    new_sessions: list[dict],
    existing_sessions: list[dict],
) -> list[dict]:
    """Report session clashes on the same calendar date."""

    conflicts: list[dict] = []

    for new in new_sessions:

        new_date = new.get(
            "date"
        )

        for existing in existing_sessions:

            if new_date != existing.get(
                "date"
            ):
                continue

            new_has_period = (
                new.get("period_start")
                is not None
            )

            existing_has_period = (
                existing.get(
                    "period_start"
                )
                is not None
            )

            overlap = False

            new_slot = ""
            existing_slot = ""

            # ----------------------------------------------------------
            # Period vs period
            # ----------------------------------------------------------

            if (
                new_has_period
                and existing_has_period
            ):

                overlap = periods_overlap(
                    new["period_start"],
                    new["period_end"],
                    existing[
                        "period_start"
                    ],
                    existing[
                        "period_end"
                    ],
                )

                new_slot = (
                    f"Hour "
                    f"{new['period_start']}-"
                    f"{new['period_end']}"
                )

                existing_slot = (
                    f"Hour "
                    f"{existing['period_start']}-"
                    f"{existing['period_end']}"
                )

            # ----------------------------------------------------------
            # Clock vs clock
            # ----------------------------------------------------------

            elif (
                new.get("start_time")
                and existing.get(
                    "start_time"
                )
            ):

                new_start = (
                    parse_time_to_minutes(
                        new["start_time"],
                        "start_time",
                    )
                )

                new_end = (
                    parse_time_to_minutes(
                        new["end_time"],
                        "end_time",
                    )
                )

                existing_start = (
                    parse_time_to_minutes(
                        existing[
                            "start_time"
                        ],
                        "start_time",
                    )
                )

                existing_end = (
                    parse_time_to_minutes(
                        existing[
                            "end_time"
                        ],
                        "end_time",
                    )
                )

                overlap = _overlaps(
                    new_start,
                    new_end,
                    existing_start,
                    existing_end,
                )

                new_slot = (
                    f"{new['start_time']}-"
                    f"{new['end_time']}"
                )

                existing_slot = (
                    f"{existing['start_time']}-"
                    f"{existing['end_time']}"
                )

            else:
                # Period-vs-clock cannot be safely compared.
                continue

            if overlap:

                conflicts.append(
                    {
                        "date": new_date,
                        "day": new.get(
                            "day"
                        ),
                        "timetable_day": new.get(
                            "timetable_day"
                        ),
                        "new_slot": new_slot,
                        "existing_slot": existing_slot,
                        "topic": new.get(
                            "topic"
                        ),
                        "reason": existing.get(
                            "reason",
                            "Overlapping session",
                        ),
                    }
                )

    return conflicts