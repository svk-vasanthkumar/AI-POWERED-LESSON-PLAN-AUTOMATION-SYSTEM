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
# A range is two dates joined by "to" (or a dash). Requiring a *second* date is
# what keeps "04.07.2026 - Tuesday Timetable" from ever looking like a range.
_DATE_RANGE_RE = re.compile(rf"\b{_DATE}\s*(?:to|through|[-–—])\s*{_DATE}\b", re.I)
_ONLY_DATE_LINE_RE = re.compile(rf"^\s*(?:{_DATE_RANGE_RE.pattern}|{_DATE})\s*$", re.I)
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
_WEEKDAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
)
_WEEKDAY_ORDER = {name: index for index, name in enumerate(_WEEKDAYS)}


# --- Event definitions --------------------------------------------------------
#
# Each row of the calendar is a single logical event. We therefore detect the
# event *label* on a line and read the date(s) that belong to that same row.
# CIA rows are handled separately because the source is inconsistent about
# spacing/capitalisation ("- III", "-III", "-II", "- II") and we must both
# normalise those and tell the *exam* range apart from the *report submission*.
_SIMPLE_EVENTS: tuple[tuple[str, str], ...] = (
    ("course_registration_confirmation", r"Confirmation\s+of\s+Course\s+Registration"),
    ("course_registration", r"Last\s+Date\s+for\s+Course\s+Registration"),
    ("exam_fee", r"Last\s+Day\s+for\s+Payment\s+of\s+Examination\s+Fee"),
    ("model_practical", r"Model\s+Practical\s+Examinations?"),
    ("remedial", r"Remedial\s*/?\s*Revision\s+Classes"),
    ("end_semester_timetable", r"Publication\s+of\s+End\s+Semester\s+Time\s*table"),
    ("model_theory", r"Model\s+Theory\s+Examinations?"),
    ("semester_end_practical", r"Semester\s+End\s+Practical\s+Examinations?"),
    ("semester_end_theory", r"Semester\s+End\s+Theory\s+Examinations?"),
    ("hall_ticket", r"Issue\s+of\s+Hall\s+Tickets?"),
    ("ia_report", r"Last\s+Date\s+for\s+submission\s+of\s+IA\s+Report\s*/?\s*CO\s+Attainment"),
    ("last_working_day", r"Last\s+Working\s+Day"),
    ("winter_vacation", r"Winter\s+Vacation"),
    ("even_semester_commencement", r"Commencement\s+of\s+EVEN\s+Semester\s+Classes"),
)
_SIMPLE_EVENT_RES = tuple(
    (event_type, re.compile(pattern, re.I)) for event_type, pattern in _SIMPLE_EVENTS
)

_CIA_LABEL_RE = re.compile(r"Continuous\s+Internal\s+Assessment", re.I)
_CIA_NUMERAL_RE = re.compile(
    r"Continuous\s+Internal\s+Assessment\s*[-–—]?\s*(III|II|I|3|2|1)",
    re.I,
)
_REPORT_RE = re.compile(r"Report\s+Submission", re.I)
_ROMAN = {"1": "I", "2": "II", "3": "III", "i": "I", "ii": "II", "iii": "III"}

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


def _line_dates(line: str) -> tuple[date | None, date | None, date | None]:
    """Return ``(single, start, end)`` for the date(s) on *this* line only.

    A range (two dates joined by ``to``/dash) yields ``(None, start, end)``; a
    lone date yields ``(single, None, None)``. Reading only the current row is
    what stops a neighbouring event's range from leaking onto a single-date
    event (and vice-versa).
    """
    range_match = _DATE_RANGE_RE.search(line)
    if range_match:
        try:
            start = _to_date(*range_match.groups()[:3])
            end = _to_date(*range_match.groups()[3:])
            return None, start, end
        except ValueError:
            return None, None, None

    date_match = _DATE_RE.search(line)
    if date_match:
        try:
            return _to_date(*date_match.groups()), None, None
        except ValueError:
            return None, None, None

    return None, None, None


def _row_dates(
    lines: list[str],
    index: int,
) -> tuple[date | None, date | None, date | None]:
    """Dates for the event on ``lines[index]``.

    Prefer dates on the label line itself. Only when the label line has no date
    at all do we fall back to an immediately-following line that contains
    *nothing but* a date/range — the way a wrapped OCR row looks. We never scan
    into a later line that carries its own text (i.e. another event's row).
    """
    single, start, end = _line_dates(lines[index])
    if single or start:
        return single, start, end

    for look in range(index + 1, min(index + 3, len(lines))):
        candidate = lines[look]
        if not candidate.strip():
            continue
        if _ONLY_DATE_LINE_RE.match(candidate):
            return _line_dates(candidate)
        break  # a line with its own text belongs to another row — stop.

    return None, None, None


def _cia_event(line: str) -> tuple[str, str, str] | None:
    """Return ``(event_type, roman_numeral, canonical_name)`` for a CIA line."""
    numeral_match = _CIA_NUMERAL_RE.search(line)
    if not numeral_match:
        return None
    roman = _ROMAN.get(numeral_match.group(1).lower(), numeral_match.group(1).upper())

    if _REPORT_RE.search(line):
        return (
            "cia_report",
            roman,
            f"Continuous Internal Assessment - {roman} Report Submission",
        )
    return ("cia", roman, f"Continuous Internal Assessment - {roman}")


def _events(text: str) -> list[CalendarEvent]:
    result: list[CalendarEvent] = []
    seen: set[tuple[str, str | None]] = set()

    lines = re.split(r"[\n\r]+", text)

    for index, line in enumerate(lines):
        if not line.strip():
            continue

        event_type: str | None = None
        event_name: str | None = None
        dedup_numeral: str | None = None

        if _CIA_LABEL_RE.search(line):
            cia = _cia_event(line)
            if cia:
                event_type, dedup_numeral, event_name = cia
        else:
            for candidate_type, regex in _SIMPLE_EVENT_RES:
                match = regex.search(line)
                if match:
                    event_type = candidate_type
                    event_name = " ".join(match.group(0).split())
                    break

        if not event_type or not event_name:
            continue

        # Normalisation guard: a canonical (type, numeral) is emitted once, even
        # when the source repeats it with different spacing/capitalisation.
        key = (event_type, dedup_numeral)
        if key in seen:
            continue

        single, start, end = _row_dates(lines, index)
        if single is None and start is None:
            continue  # never fabricate a date for a row that has none

        seen.add(key)
        result.append(
            CalendarEvent(
                type=event_type,
                name=event_name,
                date=single,
                start_date=start,
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
    seen: set[date] = set()

    # "<date> - <Weekday> Timetable" — the weekday is the timetable to APPLY on
    # that date, not the real calendar weekday (see requirement #6). Tolerate a
    # space in "Time table" and OCR dash/colon separators.
    pattern = rf"({_DATE})\s*[-–—:]?\s*({weekday_pattern})\s+Time\s*table\b"
    for match in re.finditer(pattern, text, re.I):
        try:
            special_date = _to_date(*match.groups()[1:4])
        except ValueError:
            continue
        day = match.group(5).title()
        if special_date in seen:
            continue
        seen.add(special_date)
        result.append(SpecialTimetableDay(date=special_date, timetable_day=day))

    return result


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


def _working_days(
    text: str,
    special_days: list[SpecialTimetableDay],
    semester_start: date | None,
) -> list[str]:
    """Deterministically derive the base working weekdays of the institution.

    Precedence:
      1. If the document explicitly states the working weekdays on a
         "working day(s)" line, use exactly those.
      2. Otherwise use the standard instructional week (Mon–Fri) and add
         Saturday/Sunday only when the calendar itself proves the college is in
         session on that weekday — i.e. a special-timetable substitution or the
         semester commencement falls on a real Saturday/Sunday. This is why we
         do not "silently assume Monday–Friday" (requirement #7): ACE runs
         Saturdays, and the Saturday substitution rows are the evidence.

    Nothing here is fabricated: the official per-month counts and the official
    total remain separate fields (``monthly_working_days`` / ``total_working_days``).
    """
    explicit: list[str] = []
    for line in re.split(r"[\n\r]+", text):
        # A working-days *count* line (e.g. "Total No. of Working Days 96") names
        # no weekday, so it correctly contributes nothing here.
        if re.search(r"working\s+days?", line, re.I):
            for day in _WEEKDAYS:
                if re.search(rf"\b{day}\b", line, re.I) and day not in explicit:
                    explicit.append(day)
    if explicit:
        return sorted(explicit, key=_WEEKDAY_ORDER.__getitem__)

    working: set[str] = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}

    evidence_dates: list[date] = [s.date for s in special_days]
    if semester_start:
        evidence_dates.append(semester_start)

    for evidence in evidence_dates:
        real_weekday = _WEEKDAYS[evidence.weekday()]
        if real_weekday in {"Saturday", "Sunday"}:
            working.add(real_weekday)

    return sorted(working, key=_WEEKDAY_ORDER.__getitem__)


def _semester_bounds(
    text: str,
    events: list[CalendarEvent],
) -> tuple[date | None, date | None]:
    start: date | None = None
    end: date | None = None

    # The source calendar can say "Commencement of V, VII & IX ... Semester
    # Classes" rather than naming a single semester. That still identifies the
    # ODD-semester start for the calendar being uploaded. It is anchored to the
    # *first* such commencement so the EVEN-semester row can't win.
    commencement = re.search(
        r"Commencement\s+of\s+(?!EVEN\b).{0,180}?Semester\s+Classes",
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
    special_days = _special_days(text)

    return AcademicCalendarCreate(
        academic_year=academic_year,
        semester=semester,
        semester_start=semester_start,
        semester_end=semester_end,
        working_days=_working_days(text, special_days, semester_start),
        monthly_working_days=monthly,
        total_working_days=total,
        holidays=_holidays(text),
        events=events,
        special_days=special_days,
        raw_text=text,
        extraction_method=extraction_method,
        original_filename=original_filename,
    )
