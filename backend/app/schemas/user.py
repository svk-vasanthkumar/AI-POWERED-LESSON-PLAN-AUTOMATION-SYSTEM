from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    department: str


class UserResponse(BaseModel):
    user_id: str
    name: str
    email: EmailStr
    role: str
    department: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str