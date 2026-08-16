from fastapi import APIRouter, HTTPException

from app.database import db
from app.models.user import create_user_document, UserRole
from app.schemas.user import UserRegister, UserResponse
from app.utils.password import hash_password


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
)
async def register_user(data: UserRegister):

    existing_user = await db.users.find_one(
        {
            "email": data.email.lower(),
        }
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    password_hash = hash_password(data.password)

    user = create_user_document(
        name=data.name,
        email=data.email,
        password_hash=password_hash,
        role=UserRole.FACULTY,
        department=data.department,
    )

    await db.users.insert_one(user)

    return UserResponse(
        user_id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        role=user["role"],
        department=user["department"],
    )