"""Request schemas for progress-monitoring endpoints.

Validation here gives the API controlled 422 responses for bad input (invalid
status / malformed ``actual_date``) instead of letting raw errors surface.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class SessionStatus(str, Enum):
    """The only statuses a schedule session may take (Phase 2).

    Using an Enum means FastAPI/Pydantic rejects any free-form status with a
    422 automatically — no arbitrary values are ever stored.
    """

    pending = "pending"
    completed = "completed"
    skipped = "skipped"
    rescheduled = "rescheduled"


def _normalize_optional_date(value):
    """Shared optional-``YYYY-MM-DD`` normalizer used by the schemas below."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("T", " ").split(" ")[0]
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
    raise ValueError("date must be a valid date (YYYY-MM-DD)")


class SessionStatusUpdate(BaseModel):
    """Body for ``PATCH /scheduler/{course_id}/sessions/{session_id}``.

    Records a session's teaching status plus optional execution data (Task #6
    req. 3-6). Planned fields are never overwritten — executed date, executed
    periods, actual hours, actual topics and remarks are stored separately.

    ``actual_date`` is kept for backward compatibility (the legacy re-dating
    field). For a fully validated move to another slot use the dedicated
    reschedule endpoint instead.
    """

    model_config = ConfigDict(extra="forbid")

    status: SessionStatus
    actual_date: str | None = None
    executed_date: str | None = None
    executed_period_start: int | None = None
    executed_period_end: int | None = None
    actual_hours: float | None = None
    actual_topics: str | None = None
    remarks: str | None = None

    @field_validator("actual_date", "executed_date")
    @classmethod
    def _validate_dates(cls, value):
        return _normalize_optional_date(value)


class SessionRescheduleRequest(BaseModel):
    """Body for ``POST /scheduler/{course_id}/sessions/{session_id}/reschedule``.

    Safely moves a session to another valid slot (Task #6 req. 7). The new date
    is validated against the academic calendar and, when a period is supplied,
    against the faculty timetable; the original planned slot is preserved.
    """

    model_config = ConfigDict(extra="forbid")

    new_date: str
    new_period_start: int | None = None
    new_period_end: int | None = None
    actual_topics: str | None = None
    remarks: str | None = None

    @field_validator("new_date")
    @classmethod
    def _validate_new_date(cls, value):
        normalized = _normalize_optional_date(value)
        if normalized is None:
            raise ValueError("new_date must be a valid date (YYYY-MM-DD)")
        return normalized
