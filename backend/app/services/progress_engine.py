"""Pure, deterministic progress & schedule-deviation engine.

Companion to ``scheduler_engine``: this module contains **no database or
network access and never calls an LLM**. It takes the plain list of schedule
sessions (exactly as stored inside a generated-schedule document) plus a
reference ``today`` date and derives:

  - overall progress summary (session counts + hour totals + percentages)
  - per-unit progress
  - per-topic progress
  - planned-vs-actual progress and the resulting deviation
  - a structured list of deviations (overdue / skipped / rescheduled /
    behind_schedule) with deterministic severities

Keeping this logic pure makes it fully unit-testable with fixed dates and no
MongoDB. All persistence/orchestration lives in ``progress_service``.

Session shape (produced by ``scheduler_engine.allocate_sessions``)::

    {
        "topic_id": "U1-T1",
        "topic": "Introduction to Cryptography",
        "unit_number": 1,
        "unit_title": "Introduction",
        "date": "2026-08-05",           # planned date (never overwritten)
        "day": "Monday",
        "start_time": "09:00",
        "end_time": "10:00",
        "duration_hours": 1.0,
        "status": "pending",            # pending|completed|skipped|rescheduled
        "actual_date": "2026-08-07",    # optional, only for rescheduled
    }
"""

from __future__ import annotations

from datetime import date

from app.services.scheduler_engine import parse_date

# ---------------------------------------------------------------------------
# Status vocabulary (Phase 2)
# ---------------------------------------------------------------------------

PENDING = "pending"
COMPLETED = "completed"
SKIPPED = "skipped"
RESCHEDULED = "rescheduled"

VALID_STATUSES = frozenset({PENDING, COMPLETED, SKIPPED, RESCHEDULED})
DEFAULT_STATUS = PENDING

# ---------------------------------------------------------------------------
# Status-transition rules (Task #6 req. 4)
#
# The four existing statuses are preserved. Transitions are validated so a
# session can never move into a nonsensical state without an explicit rule.
# The one deliberately-forbidden move is ``completed -> pending`` (that would
# silently erase recorded execution history); a completed session may only be
# re-recorded, rescheduled, or corrected to skipped. Re-applying the same
# status is always allowed (idempotent updates).
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    PENDING: frozenset({PENDING, COMPLETED, SKIPPED, RESCHEDULED}),
    COMPLETED: frozenset({COMPLETED, RESCHEDULED, SKIPPED}),
    SKIPPED: frozenset({SKIPPED, PENDING, COMPLETED, RESCHEDULED}),
    RESCHEDULED: frozenset({RESCHEDULED, PENDING, COMPLETED, SKIPPED}),
}


def is_valid_transition(current: str | None, new: str) -> bool:
    """Return ``True`` when moving ``current -> new`` is an allowed status move.

    An unknown/absent current status is treated as ``pending`` (the default a
    legacy session without an explicit status carries), so historical data is
    never locked out of a valid first transition.
    """
    current_status = current if current in VALID_STATUSES else DEFAULT_STATUS
    return new in ALLOWED_TRANSITIONS.get(current_status, frozenset())

# Deviation types (Phase 13)
DEV_OVERDUE = "overdue"
DEV_SKIPPED = "skipped"
DEV_RESCHEDULED = "rescheduled"
DEV_BEHIND = "behind_schedule"

# Severities (Phase 13)
SEV_LOW = "low"
SEV_MEDIUM = "medium"
SEV_HIGH = "high"


def _pct(numerator: float, denominator: float) -> float:
    """Percentage helper that avoids division by zero (Phase 6)."""
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _hours(session: dict) -> float:
    try:
        return float(session.get("duration_hours", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _executed_hours(session: dict) -> float:
    """Hours actually taught for a session (Task #6 req. 9).

    Prefers the recorded ``actual_hours`` so partial execution is respected
    (planned 2h but only 1h taught -> 1h counts). Falls back to the planned
    ``duration_hours`` for legacy completed sessions that never recorded actual
    hours, preserving their historical behaviour.
    """
    actual = session.get("actual_hours")
    if actual is not None:
        try:
            value = float(actual)
        except (TypeError, ValueError):
            return _hours(session)
        if value >= 0:
            return round(value, 2)
    return _hours(session)


def _status_of(session: dict) -> str:
    status = session.get("status") or DEFAULT_STATUS
    return status if status in VALID_STATUSES else DEFAULT_STATUS


# ---------------------------------------------------------------------------
# Summary (Phases 6, 10, 11)
# ---------------------------------------------------------------------------


def build_summary(sessions: list[dict], today: date) -> dict:
    """Aggregate session counts, hour totals and progress percentages.

    ``planned`` hours are the hours whose *planned* date has already arrived
    (``date <= today``) regardless of status — future sessions never inflate
    planned progress (Phase 11). ``completed`` hours count only ``completed``
    sessions. Deviation is ``actual - planned`` (Phase 10).
    """
    counts = {
        "total_sessions": 0,
        "completed_sessions": 0,
        "pending_sessions": 0,
        "skipped_sessions": 0,
        "rescheduled_sessions": 0,
    }

    total_planned_hours = 0.0
    completed_hours = 0.0
    hours_due_by_today = 0.0

    for session in sessions:
        status = _status_of(session)
        hours = _hours(session)

        counts["total_sessions"] += 1
        counts[f"{status}_sessions"] += 1

        total_planned_hours += hours
        if status == COMPLETED:
            # Actual (executed) hours drive real progress, not the planned
            # duration — a partially executed session counts only what was
            # actually taught (Task #6 req. 9).
            completed_hours += _executed_hours(session)

        planned_on = parse_date(session.get("date"), "date")
        if planned_on <= today:
            hours_due_by_today += hours

    total_planned_hours = round(total_planned_hours, 2)
    completed_hours = round(completed_hours, 2)
    remaining_hours = round(total_planned_hours - completed_hours, 2)

    completion_percentage = _pct(completed_hours, total_planned_hours)
    planned_progress_percentage = _pct(hours_due_by_today, total_planned_hours)
    actual_progress_percentage = completion_percentage
    deviation_percentage = round(
        actual_progress_percentage - planned_progress_percentage, 2
    )

    return {
        **counts,
        "total_planned_hours": total_planned_hours,
        "completed_hours": completed_hours,
        "remaining_hours": remaining_hours,
        "completion_percentage": completion_percentage,
        "planned_progress_percentage": planned_progress_percentage,
        "actual_progress_percentage": actual_progress_percentage,
        "deviation_percentage": deviation_percentage,
    }


# ---------------------------------------------------------------------------
# Grouped progress (Phases 7 & 8)
# ---------------------------------------------------------------------------


def build_topic_progress(sessions: list[dict]) -> list[dict]:
    """Per-topic progress, grouped by ``topic_id`` (not by name — Phase 7)."""
    groups: dict[str, dict] = {}
    order: list[str] = []

    for session in sessions:
        topic_id = session.get("topic_id")
        if topic_id not in groups:
            groups[topic_id] = {
                "topic_id": topic_id,
                "topic": session.get("topic"),
                "planned_hours": 0.0,
                "completed_hours": 0.0,
            }
            order.append(topic_id)

        hours = _hours(session)
        groups[topic_id]["planned_hours"] += hours
        if _status_of(session) == COMPLETED:
            # Count executed hours so a partially executed topic never shows as
            # 100% complete (Task #6 req. 10).
            groups[topic_id]["completed_hours"] += _executed_hours(session)

    result = []
    for topic_id in order:
        entry = groups[topic_id]
        planned = round(entry["planned_hours"], 2)
        completed = round(entry["completed_hours"], 2)
        result.append(
            {
                "topic_id": entry["topic_id"],
                "topic": entry["topic"],
                "planned_hours": planned,
                "completed_hours": completed,
                "completion_percentage": _pct(completed, planned),
            }
        )
    return result


def build_unit_progress(sessions: list[dict]) -> list[dict]:
    """Per-unit progress, grouped by ``unit_number`` (Phase 8)."""
    groups: dict = {}
    order: list = []

    for session in sessions:
        unit_number = session.get("unit_number")
        if unit_number not in groups:
            groups[unit_number] = {
                "unit_number": unit_number,
                "unit_title": session.get("unit_title"),
                "planned_hours": 0.0,
                "completed_hours": 0.0,
            }
            order.append(unit_number)

        hours = _hours(session)
        groups[unit_number]["planned_hours"] += hours
        if _status_of(session) == COMPLETED:
            # Executed hours only (Task #6 req. 10).
            groups[unit_number]["completed_hours"] += _executed_hours(session)

    result = []
    for unit_number in order:
        entry = groups[unit_number]
        planned = round(entry["planned_hours"], 2)
        completed = round(entry["completed_hours"], 2)
        result.append(
            {
                "unit_number": entry["unit_number"],
                "unit_title": entry["unit_title"],
                "planned_hours": planned,
                "completed_hours": completed,
                "completion_percentage": _pct(completed, planned),
            }
        )
    return result


# ---------------------------------------------------------------------------
# Deviation detection (Phases 9, 10, 13)
# ---------------------------------------------------------------------------


def _behind_schedule_severity(deviation_percentage: float) -> str:
    """Deterministic severity for a course that is behind plan (Phase 13)."""
    if deviation_percentage <= -15:
        return SEV_HIGH
    if deviation_percentage <= -5:
        return SEV_MEDIUM
    return SEV_LOW


def detect_deviations(
    sessions: list[dict],
    today: date,
    deviation_percentage: float,
) -> list[dict]:
    """Build the structured deviation list using deterministic rules only.

    Session-level rules:
        - overdue     : planned ``date < today`` AND status == pending  -> high
        - skipped     : status == skipped                               -> medium
        - rescheduled : status == rescheduled                           -> medium

    Course-level rule:
        - behind_schedule : emitted only when the course is behind plan
          (``deviation_percentage < 0``); severity scales with how far behind.

    Future pending sessions are never flagged overdue (Phase 9).
    """
    deviations: list[dict] = []

    for index, session in enumerate(sessions):
        status = _status_of(session)
        planned_on = parse_date(session.get("date"), "date")

        if status == PENDING and planned_on < today:
            deviations.append(
                {
                    "type": DEV_OVERDUE,
                    "severity": SEV_HIGH,
                    "session_id": index,
                    "topic_id": session.get("topic_id"),
                    "topic": session.get("topic"),
                    "planned_date": session.get("date"),
                    "status": status,
                }
            )
        elif status == SKIPPED:
            deviations.append(
                {
                    "type": DEV_SKIPPED,
                    "severity": SEV_MEDIUM,
                    "session_id": index,
                    "topic_id": session.get("topic_id"),
                    "topic": session.get("topic"),
                    "planned_date": session.get("date"),
                    "status": status,
                }
            )
        elif status == RESCHEDULED:
            deviations.append(
                {
                    "type": DEV_RESCHEDULED,
                    "severity": SEV_MEDIUM,
                    "session_id": index,
                    "topic_id": session.get("topic_id"),
                    "topic": session.get("topic"),
                    "planned_date": session.get("date"),
                    "actual_date": session.get("actual_date"),
                    "status": status,
                }
            )

    if deviation_percentage < 0:
        deviations.append(
            {
                "type": DEV_BEHIND,
                "severity": _behind_schedule_severity(deviation_percentage),
                "deviation_percentage": deviation_percentage,
            }
        )

    return deviations


# ---------------------------------------------------------------------------
# Top-level orchestration (Phase 12)
# ---------------------------------------------------------------------------


def compute_progress(sessions: list[dict], today: date) -> dict:
    """Assemble the full progress payload from schedule sessions.

    Deterministic given ``sessions`` and ``today`` — no system-date reads, no
    LLM. Safe for an empty ``sessions`` list (everything reads as zero).
    """
    sessions = sessions or []
    summary = build_summary(sessions, today)
    return {
        "summary": summary,
        "units": build_unit_progress(sessions),
        "topics": build_topic_progress(sessions),
        "deviations": detect_deviations(
            sessions, today, summary["deviation_percentage"]
        ),
    }
