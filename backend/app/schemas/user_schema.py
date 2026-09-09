from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.auth.password import validate_password_strength


class UserRegister(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    role: Literal["admin", "hod", "faculty"] = "faculty"
    department: str = Field(..., min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResetPassword(BaseModel):
    email: EmailStr
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserForgotPassword(BaseModel):
    email: EmailStr


class UserResetPasswordToken(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_token_new_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserProfileUpdate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    department: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None  # Only admins may update their email


class UserPreferencesUpdate(BaseModel):
    email_notifications: bool
    push_notifications: bool
    dark_mode: bool
