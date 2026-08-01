from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class FacultyCreate(BaseModel):
    faculty_id: str = Field(..., min_length=3)
    name: str = Field(..., min_length=3)
    email: EmailStr
    department: str
    designation: str


class FacultyUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None