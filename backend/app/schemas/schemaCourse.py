from pydantic import BaseModel, Field, field_validator


class CourseCreate(BaseModel):
    course_code: str = Field(min_length=2, max_length=30)
    course_name: str = Field(min_length=2, max_length=200)
    department: str = Field(min_length=2, max_length=100)
    semester: int = Field(ge=1, le=10)
    credits: int = Field(ge=1, le=10)
    faculty_id: str

    @field_validator(
        "course_code",
        "course_name",
        "department",
        "faculty_id",
    )
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty")

        return value


class CourseResponse(BaseModel):
    course_id: str
    course_code: str
    course_name: str
    department: str
    semester: int
    credits: int
    faculty_id: str