from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class FacultyCreate(BaseModel):
    faculty_id: str = Field(..., min_length=6, max_length=6)
    name: str = Field(..., min_length=3)
    email: EmailStr
    department: str
    designation: str
    password: Optional[str] = Field(None, min_length=6)


class FacultyUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None


class EmailCredentials(BaseModel):
    password: str = Field(..., min_length=6)