import os
import glob

# Fix unpacks
for file in glob.glob('tests/test_*.py'):
    with open(file, 'r') as f:
        content = f.read()
    
    # Fix the unpacks from (date, weekday) to (date, weekday, day_order)
    content = content.replace('for d, wd in days', 'for d, wd, _ in days')
    content = content.replace('for d, _ in days', 'for d, _, _ in days')
    content = content.replace('for d, w in days', 'for d, w, _ in days')
    content = content.replace('days[0] == (date(2026, 7, 27), "Monday")', 'days[0] == (date(2026, 7, 27), "Monday", 1)')
    
    with open(file, 'w') as f:
        f.write(content)

# Apply mock build_teachable_days wrapper to engine and engine_periods tests
wrapper = """
import app.services.scheduler_engine as se
_original_build_teachable_days = se.build_teachable_days
def _mock_build_teachable_days(cal_or_start, start_or_end, end_or_working=None, working_days=None, blocked_dates=None, special_days=None):
    if isinstance(cal_or_start, (str, __import__('datetime').date)):
        cal = {"working_days": end_or_working or [], "holidays": [{"date": d} for d in (blocked_dates or [])], "special_days": special_days or []}
        return _original_build_teachable_days(cal, cal_or_start, start_or_end)
    return _original_build_teachable_days(cal_or_start, start_or_end, end_or_working)
se.build_teachable_days = _mock_build_teachable_days
"""

for file in ['tests/test_scheduler_engine.py', 'tests/test_scheduler_engine_periods.py']:
    with open(file, 'r') as f:
        content = f.read()
    if '_mock_build_teachable_days' not in content:
        content = content.replace('import pytest', 'import pytest\n' + wrapper)
        with open(file, 'w') as f:
            f.write(content)
