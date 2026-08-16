from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = "faculty"
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

        if value != "faculty":
            raise ValueError(
                "Public registration can only create faculty users"
            )

        return value


class UserResponse(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    department: str