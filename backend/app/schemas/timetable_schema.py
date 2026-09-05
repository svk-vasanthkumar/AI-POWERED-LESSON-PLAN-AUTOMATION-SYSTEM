"""Faculty timetable request schemas.

Expands a timetable slot beyond the old ``day + start_time + end_time`` shape so
it can represent the college's period-based structure (Hour 1..7 with a lunch
break) while remaining backward compatible:

  * NEW slots are period-based: ``day`` + ``period_start`` + ``period_end``
    (1..7). A single period has ``period_start == period_end``; a lab /
    multi-period block has ``period_start < period_end`` (e.g. Hour 5-7).
  * LEGACY clock-time slots (``start_time``/``end_time``) are still accepted so
    existing timetable documents keep working and the (unmodified) scheduler
    keeps functioning until Task #5.

Validation here gives the API controlled 422 responses for malformed or
inconsistent timetable data instead of letting bad values reach the scheduler.
"""

from __future__ import annotations

from typing import Optional, Literal

from pydantic import BaseModel, field_validator, model_validator

from app.utils.timetable_periods import (
    normalize_timetable_weekday,
    periods_overlap,
    validate_period_range,
)


class ScheduleItem(BaseModel):
    """A single timetable slot.

    A slot must carry EITHER a period-based block (``period_start`` +
    ``period_end``) OR a legacy clock-time block (``start_time`` +
    ``end_time``). Period-based is preferred for new records.
    """

    day: str

    # Period-based representation (preferred).
    period_start: Optional[int] = None
    period_end: Optional[int] = None

    # Legacy clock-time representation (backward compatibility only).
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    # Optional subject/label for this slot within the course timetable. The
    # timetable's course relationship stays at the document level; this is only
    # a human-readable label (e.g. "DBMS Lab").
    subject: Optional[str] = None

    # New Logical Fields for full scheduling engine integration (Task #3)
    id: Optional[str] = None
    day_order: Optional[int] = None
    course_id: Optional[str] = None
    faculty_id: Optional[str] = None
    faculty: Optional[str] = None
    room: Optional[str] = None
    lab: Optional[str] = None
    section: Optional[str] = None
    period_timing: Optional[str] = None

    @field_validator("day")
    @classmethod
    def _validate_day(cls, value):
        # Monday-Saturday only (Sunday is not a teaching day). Raises 422.
        return normalize_timetable_weekday(value)

    @model_validator(mode="after")
    def _validate_slot(self):
        has_periods = self.period_start is not None or self.period_end is not None
        has_clock = self.start_time is not None or self.end_time is not None

        if not has_periods and not has_clock:
            raise ValueError(
                "Timetable slot must define either period_start/period_end "
                "or start_time/end_time"
            )

        if has_periods:
            if self.period_start is None or self.period_end is None:
                raise ValueError(
                    "Both period_start and period_end are required for a "
                    "period-based slot"
                )
            # Validates 1..7 range, integer type, and start <= end (rejects
            # e.g. Hour 3-2). Lunch has no period number, so it can never be
            # represented here.
            self.period_start, self.period_end = validate_period_range(
                self.period_start, self.period_end
            )

        if has_clock and not has_periods:
            # Legacy slot: require both endpoints so the existing scheduler can
            # still consume it.
            if not self.start_time or not self.end_time:
                raise ValueError(
                    "Both start_time and end_time are required for a "
                    "clock-time slot"
                )

        return self


class TimetableCreate(BaseModel):
    faculty_id: str
    course_id: str
    semester: int
    schedule: list[ScheduleItem] = []
    
    status: Literal["OCR_PENDING", "DRAFT", "VERIFIED", "REJECTED"] = "VERIFIED"
    raw_text: Optional[str] = None
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    extraction_method: Optional[str] = None

    @model_validator(mode="after")
    def _validate_no_internal_overlap(self):
        # No two period-based slots on the same weekday may share a period
        # (Task #4, validation rule: "no overlapping periods inside the same
        # timetable"). Legacy clock-only slots are not period-checked here.
        by_day: dict[str, list[tuple[int, int]]] = {}
        for item in self.schedule:
            if item.period_start is None or item.period_end is None:
                continue
            existing = by_day.setdefault(item.day, [])
            for other_start, other_end in existing:
                if periods_overlap(
                    item.period_start, item.period_end, other_start, other_end
                ):
                    raise ValueError(
                        f"Overlapping periods on {item.day}: "
                        f"Hour {item.period_start}-{item.period_end} conflicts "
                        f"with Hour {other_start}-{other_end}"
                    )
            existing.append((item.period_start, item.period_end))
        return self


class TimetableUpdate(BaseModel):
    """Partial-update payload for a timetable.

    All fields are optional. When ``schedule`` is supplied it fully replaces the
    stored schedule and is validated exactly like create (internal overlap +
    per-slot rules).
    """

    faculty_id: Optional[str] = None
    course_id: Optional[str] = None
    semester: Optional[int] = None
    schedule: Optional[list[ScheduleItem]] = None
    
    status: Optional[Literal["OCR_PENDING", "DRAFT", "VERIFIED", "REJECTED"]] = None
    raw_text: Optional[str] = None
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    extraction_method: Optional[str] = None

    @model_validator(mode="after")
    def _validate_no_internal_overlap(self):
        if self.schedule is None:
            return self
        by_day: dict[str, list[tuple[int, int]]] = {}
        for item in self.schedule:
            if item.period_start is None or item.period_end is None:
                continue
            existing = by_day.setdefault(item.day, [])
            for other_start, other_end in existing:
                if periods_overlap(
                    item.period_start, item.period_end, other_start, other_end
                ):
                    raise ValueError(
                        f"Overlapping periods on {item.day}: "
                        f"Hour {item.period_start}-{item.period_end} conflicts "
                        f"with Hour {other_start}-{other_end}"
                    )
            existing.append((item.period_start, item.period_end))
        return self
