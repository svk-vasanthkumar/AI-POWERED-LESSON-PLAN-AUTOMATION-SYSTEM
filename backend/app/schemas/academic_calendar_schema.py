from datetime import date as Date
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from app.utils.calendar_dates import normalize_weekday, to_date


class DateRange(BaseModel):
    start_date: Date
    end_date: Date
    name: str | None = None

    @field_validator("end_date")
    @classmethod
    def validate_range(cls, value, info):
        start_date = info.data.get("start_date")
        if start_date and value < start_date:
            raise ValueError("end_date must be on or after start_date")
        return value


class CalendarHoliday(BaseModel):
    date: Date
    name: str = Field(..., min_length=1)


class CalendarEvent(BaseModel):
    type: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)

    date: Date | None = None
    start_date: Date | None = None
    end_date: Date | None = None

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, value, info):
        start_date = info.data.get("start_date")

        if start_date and value and value < start_date:
            raise ValueError("end_date cannot be before start_date")

        return value


class SpecialTimetableDay(BaseModel):
    date: Date
    timetable_day: str = Field(..., min_length=1)

    @field_validator("timetable_day")
    @classmethod
    def validate_day(cls, value):
        return normalize_weekday(value)


class MonthlyWorkingDays(BaseModel):
    month: str = Field(..., min_length=1)
    working_days: int = Field(..., ge=0)


class AcademicCalendarCreate(BaseModel):
    academic_year: str = Field(..., min_length=9, max_length=9, pattern=r"^20\d{2}-20\d{2}$")

    semester: int = Field(
        ...,
        ge=1,
        le=10,
    )

    semester_start: Date
    semester_end: Date

    working_days: list[str] = Field(default_factory=list)

    monthly_working_days: list[MonthlyWorkingDays] = Field(
        default_factory=list
    )

    total_working_days: int | None = Field(
        default=None,
        ge=0,
    )

    holidays: list[CalendarHoliday] = Field(
        default_factory=list
    )

    events: list[CalendarEvent] = Field(
        default_factory=list
    )

    special_days: list[SpecialTimetableDay] = Field(
        default_factory=list
    )

    cia_1: DateRange | None = None
    cia_2: DateRange | None = None
    cia_3: DateRange | None = None
    model_practical: DateRange | None = None
    model_theory: DateRange | None = None
    semester_end_practical: DateRange | None = None
    semester_end_theory: DateRange | None = None
    winter_vacation: DateRange | None = None

    internal_exams: list[str] = Field(default_factory=list)

    raw_text: str | None = None
    extraction_method: str | None = None
    original_filename: str | None = None

    @field_validator("semester_end")
    @classmethod
    def validate_semester_dates(cls, value, info):
        start_date = info.data.get("semester_start")

        if start_date and value < start_date:
            raise ValueError(
                "semester_end must be on or after semester_start"
            )

        return value

    @field_validator("working_days")
    @classmethod
    def validate_working_days(cls, value):
        normalized = []
        for day in value:
            normalized.append(normalize_weekday(day))
        return normalized

    @field_validator("holidays")
    @classmethod
    def validate_holidays(cls, value):
        seen = set()
        for holiday in value:
            d = holiday.date
            if d in seen:
                raise ValueError(f"Duplicate holiday date: {d}")
            seen.add(d)
        return value

    @field_validator("internal_exams")
    @classmethod
    def validate_internal_exams(cls, value):
        for item in value:
            to_date(item)
        return value

    @field_validator("cia_1", "cia_2", "cia_3", "model_practical", "model_theory", "semester_end_practical", "semester_end_theory", "winter_vacation")
    @classmethod
    def validate_range_within_bounds(cls, value, info):
        if value is not None:
            sem_start = info.data.get("semester_start")
            sem_end = info.data.get("semester_end")
            if sem_start and value.start_date < sem_start:
                raise ValueError("Date range must fall within the semester bounds")
            if sem_end and value.end_date > sem_end:
                raise ValueError("Date range must fall within the semester bounds")
        return value


class AcademicCalendarUpdate(BaseModel):
    semester_start: Date | None = None
    semester_end: Date | None = None

    working_days: list[str] | None = None

    monthly_working_days: list[MonthlyWorkingDays] | None = None

    total_working_days: int | None = Field(
        default=None,
        ge=0,
    )

    holidays: list[CalendarHoliday] | None = None
    events: list[CalendarEvent] | None = None
    special_days: list[SpecialTimetableDay] | None = None

    cia_1: DateRange | None = None
    cia_2: DateRange | None = None
    cia_3: DateRange | None = None
    model_practical: DateRange | None = None
    model_theory: DateRange | None = None
    semester_end_practical: DateRange | None = None
    semester_end_theory: DateRange | None = None
    winter_vacation: DateRange | None = None

    internal_exams: list[str] | None = None


class AcademicCalendarUploadResponse(BaseModel):
    calendar_id: str
    filename: str
    extraction_method: str
    extraction_status: Literal[
        "success",
        "needs_review",
        "failed",
    ]

    parsed_calendar: AcademicCalendarCreate
    raw_text: str


class AcademicCalendarPreviewResponse(BaseModel):
    calendar_id: str
    status: Literal[
        "pending_review",
        "confirmed",
        "rejected",
    ]

    calendar: AcademicCalendarCreate