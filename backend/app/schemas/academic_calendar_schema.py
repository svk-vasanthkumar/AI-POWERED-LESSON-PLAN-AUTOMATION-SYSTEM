from pydantic import BaseModel


class AcademicCalendarCreate(BaseModel):
    academic_year: str
    semester: int
    semester_start: str
    semester_end: str
    working_days: list[str]
    holidays: list[str]
    internal_exams: list[str]