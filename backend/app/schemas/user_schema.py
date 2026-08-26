from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)

    role: Literal["admin", "hod", "faculty"] = "faculty"

    department: str = Field(..., min_length=2, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResetPassword(BaseModel):
    email: EmailStr
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=100)


class UserForgotPassword(BaseModel):
    email: EmailStr


class UserResetPasswordToken(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6, max_length=100)


class UserProfileUpdate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    department: str = Field(..., min_length=2, max_length=100)


class UserPreferencesUpdate(BaseModel):
    email_notifications: bool
    push_notifications: bool
    dark_mode: bool
