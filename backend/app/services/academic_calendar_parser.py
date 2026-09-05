from __future__ import annotations

import re
from datetime import date

from app.schemas.academic_calendar_schema import (
    AcademicCalendarCreate,
    CalendarEvent,
    CalendarHoliday,
    MonthlyWorkingDays,
    SpecialTimetableDay,
)


# Accept the common formats used by college calendars and OCR output:
# 01.07.2026, 01/07/2026, 01-07-2026.
_DATE = r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})"
_DATE_RE = re.compile(rf"\b{_DATE}\b")
_DATE_RANGE_RE = re.compile(rf"\b{_DATE}\s*(?:to|[-–—])\s*{_DATE}\b", re.I)
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
_WEEKDAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
)


_EVENT_PATTERNS = (
    ("course_registration", r"Last\s+Date\s+for\s+Course\s+Registration(?!\s+Confirmation)"),
    ("course_registration_confirmation", r"Confirmation\s+of\s+Course\s+Registration"),
    ("cia_report", r"Continuous\s+Internal\s+Assessment\s*[-–]?\s*(?:I{1,3}|1{1,3})\s+Report\s+Submission"),
    ("cia", r"Continuous\s+Internal\s+Assessment\s*[-–]?\s*(?:I{1,3}|1{1,3})(?!\s+Report)"),
    ("model_practical", r"Model\s+Practical\s+Examination"),
    ("remedial", r"Remedial\s*/\s*Revision\s+Classes"),
    ("end_semester_timetable", r"Publication\s+of\s+End\s+Semester\s+Timetable"),
    ("model_theory", r"Model\s+Theory\s+Examination"),
    ("last_working_day", r"Last\s+Working\s+Day"),
    ("semester_end_practical", r"Semester\s+End\s+Practical\s+Examinations?"),
    ("hall_ticket", r"Issue\s+of\s+Hall\s+tickets?"),
    ("ia_report", r"Last\s+Date\s+for\s+submission\s+of\s+IA\s+Report\s*/?\s*CO\s+Attainment"),
    ("semester_end_theory", r"Semester\s+End\s+Theory\s+Examinations?"),
    ("winter_vacation", r"Winter\s+Vacation"),
    ("even_semester_commencement", r"Commencement\s+of\s+EVEN\s+Semester\s+Classes"),
)

_HOLIDAY_NAMES = (
    "Independence Day",
    "Milad-un-Nabi",
    "Krishna Jayanthi",
    "Vinayakar Chathurthi",
    "Gandhi Jayanthi",
    "Ayutha Pooja",
    "Vijaya Dasami",
    "Deepavali",
    "Christmas",
    "New Year",
)


def _to_date(day: str, month: str, year: str) -> date:
    return date(int(year), int(month), int(day))


def _parse_date_text(value: str) -> date | None:
    match = _DATE_RE.search(value or "")
    if not match:
        return None
    try:
        return _to_date(*match.groups())
    except ValueError:
        return None


def _academic_year(text: str) -> str | None:
    match = re.search(r"\b(20\d{2})\s*[-–—]\s*(20\d{2})\b", text, re.I)
    return f"{match.group(1)}-{match.group(2)}" if match else None


def _semester(text: str) -> int | None:
    roman_to_int = {
        'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
        'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10
    }
    
    # 1. Match "III Semester" or "3rd Semester"
    match = re.search(r"\b(I{1,3}|IV|V|VI{1,3}|IX|X|\d{1,2}(?:st|nd|rd|th)?)\s+SEMESTER\b", text, re.I)
    if match:
        val = match.group(1).upper()
        # Remove suffixes like ST, ND, RD, TH
        val = re.sub(r"(ST|ND|RD|TH)$", "", val)
        if val.isdigit():
            return int(val)
        return roman_to_int.get(val)

    # 2. Match "Semester III" or "Semester 3"
    match = re.search(r"\bSEMESTER\s*[:=-]?\s*(I{1,3}|IV|V|VI{1,3}|IX|X|\d{1,2})\b", text, re.I)
    if match:
        val = match.group(1).upper()
        if val.isdigit():
            return int(val)
        return roman_to_int.get(val)

    # 3. Fallbacks for OCR errors (e.g. VIL for VII)
    patterns = (
        (r"\bVIL\b", 7),
        (r"\bVI[I1]\b\s*(?:,|&|AND)", 7),
        (r"\bVII\b", 7),
        (r"\bIII\b", 3),
        (r"\bII\b", 2),
        (r"\bIV\b", 4),
        (r"\bVI\b", 6),
        (r"\bV\b", 5),
        (r"\bI\b", 1),
    )
    for pattern, value in patterns:
        if re.search(pattern, text, re.I):
            return value
    return None


def _working_days(text: str) -> list[str]:
    """Extract base working weekdays only when the document states them.

    We deliberately do not treat special timetable entries such as
    "17.08.2026 - Thursday Timetable" as proof that Thursday is a base working
    day. That would silently invent data from the source document.
    """
    candidates: list[str] = []
    for line in re.split(r"[\n\r]+", text):
        if re.search(r"working\s+days?", line, re.I):
            for day in _WEEKDAYS:
                if re.search(rf"\b{day}\b", line, re.I) and day not in candidates:
                    candidates.append(day)
    return candidates


def _monthly_working_days(text: str) -> tuple[list[MonthlyWorkingDays], int | None]:
    month_rows: list[MonthlyWorkingDays] = []
    seen: set[str] = set()

    # Works both for normal OCR text ("July 27") and table extraction where
    # the month and count are separated by a small amount of whitespace.
    for match in re.finditer(rf"\b({_MONTHS})\b\s*[:|\-]?\s*(\d{{1,3}})\b", text, re.I):
        name = match.group(1).title()
        days = int(match.group(2))
        if days <= 31 and name not in seen:
            seen.add(name)
            month_rows.append(MonthlyWorkingDays(month=name, working_days=days))

    total_match = re.search(
        r"Total\s+No\.?\s+of\s+Working\s+Days(?:\D{0,80})(\d{1,3})\b",
        text,
        re.I,
    )
    total = int(total_match.group(1)) if total_match else None
    return month_rows, total


def _nearest_dates(
    context: str,
    target_position: int | None = None,
    prefer_after: int | None = None,
) -> tuple[date | None, date | None]:
    target = target_position if target_position is not None else len(context) // 2
    ranges = list(_DATE_RANGE_RE.finditer(context))
    if ranges:
        after = [item for item in ranges if prefer_after is not None and item.start() >= prefer_after]
        candidates = after or ranges
        match = min(candidates, key=lambda item: abs(item.start() - target))
        try:
            return _to_date(*match.groups()[:3]), _to_date(*match.groups()[3:])
        except ValueError:
            return None, None

    dates = list(_DATE_RE.finditer(context))
    if dates:
        match = min(dates, key=lambda item: abs(item.start() - target))
        try:
            return _to_date(*match.groups()), None
        except ValueError:
            return None, None

    return None, None


def _events(text: str) -> list[CalendarEvent]:
    result: list[CalendarEvent] = []
    seen: set[tuple[str, str, date | None, date | None]] = set()

    for event_type, pattern in _EVENT_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            # A calendar row can be represented as separate OCR lines. Search
            # a bounded window around the event rather than assuming the date
            # is on the same line.
            left = max(0, match.start() - 180)
            right = min(len(text), match.end() + 220)
            context = text[left:right]
            start, end = _nearest_dates(
                context,
                match.start() - left,
                prefer_after=match.end() - left,
            )

            event_name = " ".join(match.group(0).split())
            key = (event_type, event_name.lower(), start, end)
            if key in seen:
                continue
            seen.add(key)

            result.append(
                CalendarEvent(
                    type=event_type,
                    name=event_name,
                    date=start if end is None else None,
                    start_date=start if end is not None else None,
                    end_date=end,
                )
            )

    return result


def _holidays(text: str) -> list[CalendarHoliday]:
    result: list[CalendarHoliday] = []
    seen: set[date] = set()

    for name in _HOLIDAY_NAMES:
        pattern = rf"({_DATE})\s*[-–—:]\s*{re.escape(name)}\b"
        for match in re.finditer(pattern, text, re.I):
            try:
                holiday_date = _to_date(*match.groups()[1:4])
            except ValueError:
                continue
            if holiday_date in seen:
                continue
            seen.add(holiday_date)
            result.append(CalendarHoliday(date=holiday_date, name=name))

    return result


def _special_days(text: str) -> list[SpecialTimetableDay]:
    weekday_pattern = "|".join(_WEEKDAYS)
    result: list[SpecialTimetableDay] = []
    seen: set[tuple[date, str]] = set()

    # Pattern 1: Explicit timetable day (e.g., "17.08.2026 - Thursday Timetable")
    pattern = rf"({_DATE})\s*[-–—:]\s*({weekday_pattern})\s+Timetable\b"
    for match in re.finditer(pattern, text, re.I):
        try:
            special_date = _to_date(*match.groups()[1:4])
        except ValueError:
            continue
        day = match.group(5).title()
        key = (special_date, day)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            SpecialTimetableDay(
                date=special_date,
                timetable_day=day,
            )
        )
        
    # Pattern 2: Day Order N (e.g., "17.08.2026 - Day Order 4")
    day_order_map = {
        "1": "Monday", "I": "Monday",
        "2": "Tuesday", "II": "Tuesday",
        "3": "Wednesday", "III": "Wednesday",
        "4": "Thursday", "IV": "Thursday",
        "5": "Friday", "V": "Friday",
        "6": "Saturday", "VI": "Saturday",
    }
    
    for line in re.split(r"[\n\r]+", text):
        date_match = re.search(_DATE, line, re.I)
        if not date_match:
            continue
            
        order_match = re.search(r"Day\s*Order\s*[-–—:]?\s*([1-6IV]+)\b", line, re.I)
        if not order_match:
            continue
            
        try:
            special_date = _to_date(*date_match.groups()[1:4])
        except ValueError:
            continue
            
        order_val = order_match.group(1).upper()
        day = day_order_map.get(order_val)
        if not day:
            continue
            
        key = (special_date, day)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            SpecialTimetableDay(
                date=special_date,
                timetable_day=day,
            )
        )

    return result


def _semester_bounds(
    text: str,
    events: list[CalendarEvent],
) -> tuple[date | None, date | None]:
    start: date | None = None
    end: date | None = None

    # The source calendar can say "Commencement of V, VII & IX ... Semester
    # Classes" rather than naming a single semester. That still identifies the
    # ODD-semester start for the calendar being uploaded.
    commencement = re.search(
        r"Commencement\s+of\s+.{0,180}?Semester\s+Classes",
        text,
        re.I | re.S,
    )
    if commencement:
        start = _parse_date_text(text[commencement.end() : commencement.end() + 120])

    theory = [
        event.end_date
        for event in events
        if event.type == "semester_end_theory" and event.end_date
    ]
    if theory:
        end = max(theory)

    # If theory dates are absent, the last working day is a safer fallback than
    # guessing an academic-term end from the document title.
    last_working = [
        event.date
        for event in events
        if event.type == "last_working_day" and event.date
    ]
    if end is None and last_working:
        end = max(last_working)

    return start, end


def parse_academic_calendar_text(
    text: str,
    *,
    original_filename: str | None = None,
    extraction_method: str | None = None,
) -> AcademicCalendarCreate:
    if not text or not text.strip():
        raise ValueError("Academic calendar contains no readable text.")

    academic_year = _academic_year(text)
    semester = _semester(text)
    if not academic_year or semester is None:
        raise ValueError(
            "Unable to identify the academic year and semester from the document."
        )

    events = _events(text)
    semester_start, semester_end = _semester_bounds(text, events)
    if not semester_start or not semester_end:
        raise ValueError(
            "Unable to identify the semester start and end dates from the document."
        )

    monthly, total = _monthly_working_days(text)

    return AcademicCalendarCreate(
        academic_year=academic_year,
        semester=semester,
        semester_start=semester_start,
        semester_end=semester_end,
        working_days=_working_days(text),
        monthly_working_days=monthly,
        total_working_days=total,
        holidays=_holidays(text),
        events=events,
        special_days=_special_days(text),
        raw_text=text,
        extraction_method=extraction_method,
        original_filename=original_filename,
    )
