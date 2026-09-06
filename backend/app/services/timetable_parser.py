import re

_DAY_MAP = {
    "monday": "Monday", "mon": "Monday",
    "tuesday": "Tuesday", "tue": "Tuesday",
    "wednesday": "Wednesday", "wed": "Wednesday",
    "thursday": "Thursday", "thu": "Thursday",
    "friday": "Friday", "fri": "Friday",
    "saturday": "Saturday", "sat": "Saturday"
}

def parse_timetable_text(text: str) -> list[dict]:
    """
    Heuristically parse raw OCR text from a timetable into structured slots.
    Returns a list of slot dictionaries.
    """
    slots = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    
    current_day = None
    current_period = 1
    
    for i, line in enumerate(lines):
        lower_line = line.lower()
        
        # 1. Check if line is a day
        found_day = False
        for key, full_day in _DAY_MAP.items():
            # Match exactly or if it starts with the day name
            if lower_line == key or lower_line.startswith(key + " "):
                current_day = full_day
                found_day = True
                current_period = 1 # Reset period for new day
                
                # Check if subject is on the same line (e.g. "Mon OOPS LAB")
                remaining = line[len(key):].strip(" -:|")
                if len(remaining) > 2 and not remaining.isdigit():
                    slots.append({
                        "day": current_day,
                        "period_start": current_period,
                        "period_end": current_period,
                        "subject": remaining,
                        "faculty": "",
                        "room": ""
                    })
                    current_period += 1
                break
                
        if found_day:
            continue
            
        # 2. Skip headers and noise
        if "lunch" in lower_line or "staff" in lower_line or "hour" in lower_line or "day" in lower_line:
            continue
            
        # 3. Look for explicit period markers (1-7)
        period_match = re.search(r'\b(?:hour|period|p|hr|h)?\s*([1-7])\b', line, re.IGNORECASE)
        if period_match:
            current_period = int(period_match.group(1))
            
            # If there's more text on the line, it's a subject
            remaining = line[:period_match.start()] + line[period_match.end():]
            remaining = remaining.strip(" -:|")
            if len(remaining) > 2 and current_day:
                slots.append({
                    "day": current_day,
                    "period_start": current_period,
                    "period_end": current_period,
                    "subject": remaining,
                    "faculty": "",
                    "room": ""
                })
                current_period += 1
            continue
            
        # 4. If we have a current day, and the line has length > 3, it's likely a subject
        if current_day and len(line) > 3 and not line.isdigit():
            # Check for combined subjects like "OOPS&ETHICAL HACKING LAB -LAB V1"
            slots.append({
                "day": current_day,
                "period_start": current_period,
                "period_end": current_period,
                "subject": line,
                "faculty": "",
                "room": ""
            })
            current_period += 1
            if current_period > 7:
                current_period = 1
            
    return slots
