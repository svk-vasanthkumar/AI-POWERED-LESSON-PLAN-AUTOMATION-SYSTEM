from pydantic import BaseModel


class CourseCreate(BaseModel):
    course_code: str
    course_name: str
    department: str
    semester: int
    credits: int
    faculty_ids: list[str]
    academic_year: str
    short_form: str | None = None


class CourseUpdate(BaseModel):
    course_code: str
    course_name: str
    department: str
    semester: int
    credits: int
    faculty_ids: list[str]
    academic_year: str
    short_form: str | None = None