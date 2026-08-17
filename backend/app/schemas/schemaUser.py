from pydantic import BaseModel, EmailStr, Field, field_validator


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


class ManagementUserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str
    department: str = Field(min_length=2, max_length=100)

    @field_validator("name", "department")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty")

        return value

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        value = value.lower().strip()

        if value not in {"faculty", "hod"}:
            raise ValueError("Role must be faculty or hod")

        return value