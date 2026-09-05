"""Academic Calendar Date Resolver.

Makes the Academic Calendar the authoritative source for date -> day/order resolution.
"""
from datetime import date
from typing import TypedDict, Optional

from app.schemas.academic_calendar_schema import AcademicCalendarCreate

class DateResolution(TypedDict):
    date: date
    day: str
    is_working_day: bool
    holiday: bool
    day_order: Optional[int]
    special_day_order: Optional[int]
    effective_day_order: Optional[int]
    effective_day: str

def resolve_date(calendar, target_date: date) -> DateResolution:
    """
    Dynamically resolve a date against an academic calendar.
    No hardcoded days or orders.
    """
    # Accept both Pydantic models and raw dicts (for tests/legacy data)
    if hasattr(calendar, "model_dump"):
        calendar = calendar.model_dump()
        
    actual_day = target_date.strftime("%A")
    
    holidays = calendar.get("holidays", [])
    special_days = calendar.get("special_days", [])
    working_days = calendar.get("working_days", [])
    
    # Check if holiday
    is_holiday = False
    for h in holidays:
        h_date = h.get("date") if isinstance(h, dict) else (h.date if hasattr(h, 'date') else h)
        if hasattr(h_date, "date"):
            h_date = h_date.date()
        elif isinstance(h_date, str):
            from datetime import datetime
            h_date = datetime.strptime(h_date.split("T")[0], "%Y-%m-%d").date()
        if h_date == target_date:
            is_holiday = True
            break
            
    # Check for special day
    special_day = None
    for sd in special_days:
        sd_date = sd.get("date") if isinstance(sd, dict) else (sd.date if hasattr(sd, 'date') else sd)
        if hasattr(sd_date, "date"):
            sd_date = sd_date.date()
        elif isinstance(sd_date, str):
            from datetime import datetime
            sd_date = datetime.strptime(sd_date.split("T")[0], "%Y-%m-%d").date()
        if sd_date == target_date:
            special_day = sd
            break
            
    # Determine Effective Day
    effective_day = actual_day
    if special_day:
        effective_day = special_day.get("timetable_day") if isinstance(special_day, dict) else special_day.timetable_day
        
    # Check if working day
    is_working = effective_day in working_days and not is_holiday
    
    # Determine Day Orders
    try:
        normal_day_order = working_days.index(actual_day) + 1
    except ValueError:
        normal_day_order = None
        
    special_day_order = None
    if special_day:
        try:
            special_day_order = working_days.index(effective_day) + 1
        except ValueError:
            pass
            
    effective_day_order = special_day_order if special_day else normal_day_order
    
    return {
        "date": target_date,
        "day": actual_day,
        "is_working_day": is_working,
        "holiday": is_holiday,
        "day_order": normal_day_order,
        "special_day_order": special_day_order,
        "effective_day_order": effective_day_order,
        "effective_day": effective_day
    }
