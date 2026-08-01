from pydantic import BaseModel


class ScheduleItem(BaseModel):
    day: str
    start_time: str
    end_time: str


class TimetableCreate(BaseModel):
    faculty_id: str
    course_id: str
    semester: int
    schedule: list[ScheduleItem]