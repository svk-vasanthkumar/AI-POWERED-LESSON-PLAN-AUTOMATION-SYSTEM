from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.auth.password import validate_password_strength


class FacultyCreate(BaseModel):
    faculty_id: str = Field(..., min_length=6, max_length=6)
    name: str = Field(..., min_length=3)
    email: EmailStr
    department: str
    designation: str
    password: Optional[str] = Field(None, min_length=8)

    @field_validator("password")
    @classmethod
    def validate_pwd(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return validate_password_strength(v)
        return v


class FacultyUpdate(BaseModel):
    faculty_id: Optional[str] = Field(None, min_length=6, max_length=6)
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)

    @field_validator("password")
    @classmethod
    def validate_pwd(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return validate_password_strength(v)
        return v


class EmailCredentials(BaseModel):
    password: str = Field(..., min_length=6)