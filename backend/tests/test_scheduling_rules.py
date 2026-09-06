from datetime import date
from app.services.scheduler_engine import build_period_blocks, apply_exam_overrides
from app.utils.scheduling_rules import ScheduleType

def test_saturday_limits():
    """Verify Saturday blocks exclude hours 5-7 and are capped at 4 hours."""
    teachable_days = [(date(2023, 10, 14), "Saturday", 1)]
    
    # Simulate a timetable that requests full 7 periods on Saturday
    period_slots = {"Order:1": [(1, 7)], "Saturday": [(1, 7)]}
    
    blocks = build_period_blocks(teachable_days, period_slots)
    
    assert len(blocks) == 1
    assert blocks[0]["period_start"] == 1
    assert blocks[0]["period_end"] == 4
    assert blocks[0]["capacity"] == 4.0

def test_cia_exam_overrides():
    """Verify CIA exam configuration splits blocks into exam and class sessions."""
    teachable_days = [
        (date(2023, 10, 16), "Monday", 1),
        (date(2023, 10, 21), "Saturday", 6)
    ]
    
    # Monday has 7 periods, Saturday now capped at 4
    period_slots = {
        "Monday": [(1, 7)],
        "Order:6": [(1, 4)],
        "Saturday": [(1, 4)]
    }
    
    blocks = build_period_blocks(teachable_days, period_slots)
    
    # Exam config targeting Monday and Saturday
    exam_configs = [{
        "start_date": "2023-10-16",
        "end_date": "2023-10-21",
        "exam_days": ["Monday", "Saturday"]
    }]
    
    processed = apply_exam_overrides(blocks, exam_configs)
    
    # Monday should be split into: Exam (1-2) + Class (3-7)
    monday_blocks = [b for b in processed if b["day"] == "Monday"]
    assert len(monday_blocks) == 2
    assert monday_blocks[0]["session_type"] == ScheduleType.EXAM.value
    assert monday_blocks[0]["capacity"] == 2.0
    
    assert monday_blocks[1]["session_type"] == ScheduleType.CLASS.value
    assert monday_blocks[1]["period_start"] == 3
    assert monday_blocks[1]["period_end"] == 7
    assert monday_blocks[1]["capacity"] == 5.0
    
    # Saturday should be split into: Exam (1-2) + Class (3-4)
    saturday_blocks = [b for b in processed if b["day"] == "Saturday"]
    assert len(saturday_blocks) == 2
    assert saturday_blocks[0]["session_type"] == ScheduleType.EXAM.value
    assert saturday_blocks[0]["capacity"] == 2.0
    
    assert saturday_blocks[1]["session_type"] == ScheduleType.CLASS.value
    assert saturday_blocks[1]["period_start"] == 3
    assert saturday_blocks[1]["period_end"] == 4
    assert saturday_blocks[1]["capacity"] == 2.0
