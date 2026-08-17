from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import db
from app.models.user import UserRole, create_user_document
from app.schemas.user import (
    LoginResponse,
    ManagementUserCreate,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.utils.auth import require_roles
from app.utils.jwt import create_access_token, decode_access_token
from app.utils.password import hash_password, verify_password

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

security = HTTPBearer()


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


@router.post(
    "/login",
    response_model=LoginResponse,
)
async def login_user(data: UserLogin):
    user = await db.users.find_one(
        {
            "email": data.email.lower(),
        }
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    if not verify_password(
        data.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    token = create_access_token(
        user_id=str(user["_id"]),
        role=user["role"],
        email=user["email"],
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
    )


@router.get("/profile")
async def profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    user = await db.users.find_one(
        {
            "_id": ObjectId(payload["sub"]),
        }
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User no longer exists",
        )

    return {
        "message": "Authorized",
        "user": {
            "id": str(user["_id"]),
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "department": user["department"],
        },
    }


@router.post("/admin/users")
async def create_management_user(
    data: ManagementUserCreate,
    current_user=Depends(require_roles("admin")),
):
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

    user = create_user_document(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole(data.role),
        department=data.department,
    )

    await db.users.insert_one(user)

    return {
        "message": "User created successfully",
        "user": {
            "id": str(user["_id"]),
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "department": user["department"],
        },
    }