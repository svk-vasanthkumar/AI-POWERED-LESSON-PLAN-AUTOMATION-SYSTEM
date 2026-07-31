from fastapi import APIRouter, Depends, HTTPException

from app.auth.jwt import verify_token
from app.schemas.user_schema import UserLogin, UserRegister
from app.services.auth_service import login_user, register_user

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post("/register")
async def register(user: UserRegister):
    try:
        return await register_user(user)

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post("/login")
async def login(user: UserLogin):
    try:
        return await login_user(
            user.email,
            user.password,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
        )


@router.get("/profile")
async def profile(user=Depends(verify_token)):
    return {
        "message": "Authorized",
        "user": user,
    }