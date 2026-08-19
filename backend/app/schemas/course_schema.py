from pydantic import BaseModel


class CourseCreate(BaseModel):
    course_code: str
    course_name: str
    department: str
    semester: int
    credits: int
    faculty_id: str


class CourseUpdate(BaseModel):
    course_name: str
    department: str
    semester: int
    credits: int
    faculty_id: str