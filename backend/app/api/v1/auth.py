from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.schemas.user_schema import (
    UserLogin, 
    UserRegister, 
    UserResetPassword,
    UserForgotPassword,
    UserResetPasswordToken,
    UserProfileUpdate,
    UserPreferencesUpdate
)
from app.services.auth_service import (
    login_user, 
    register_user, 
    reset_password,
    handle_forgot_password,
    handle_reset_password_token,
    update_user_profile,
    update_user_preferences,
    verify_email_token_service,
)

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


@router.post("/reset-password")
async def reset_password_route(user: UserResetPassword):
    try:
        return await reset_password(
            user.email,
            user.current_password,
            user.new_password,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.post("/forgot-password")
async def forgot_password_route(data: UserForgotPassword):
    try:
        await handle_forgot_password(data.email)
        # Always return success to prevent email enumeration
        return {"message": "If an account exists, a reset link has been sent."}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/reset-password-token")
async def reset_password_token_route(data: UserResetPasswordToken):
    try:
        await handle_reset_password_token(data.token, data.new_password)
        return {"message": "Password reset successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.get("/profile")
async def profile(user=Depends(get_current_user)):
    return {
        "message": "Authorized",
        "user": user,
    }


@router.put("/profile")
async def update_profile(data: UserProfileUpdate, user=Depends(get_current_user)):
    try:
        return await update_user_profile(
            current_email=user["email"],
            name=data.name,
            department=data.department,
            new_email=data.email,
            role=user["role"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.put("/preferences")
async def update_preferences(data: UserPreferencesUpdate, user=Depends(get_current_user)):
    try:
        return await update_user_preferences(user["email"], data.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Email Verification ────────────────────────────────────────────────────────

class VerifyEmailRequest(BaseModel):
    token: str

class ResendVerificationRequest(BaseModel):
    email: str

@router.post("/verify-email")
async def verify_email(data: VerifyEmailRequest):
    """Confirm a user's email address using the token from the verification email."""
    try:
        return await verify_email_token_service(data.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/resend-verification")
async def resend_verification(data: ResendVerificationRequest):
    """Resend the email verification link for users who didn't receive it."""
    from app.database.mongodb import get_database
    from app.auth.jwt import create_email_verification_token
    from app.services.email_service import send_verification_email

    db = get_database()
    user = await db.users.find_one({"email": data.email.lower()})
    # Always return success to prevent email enumeration
    if user and not user.get("is_email_verified"):
        token = create_email_verification_token(data.email)
        send_verification_email(data.email, token, user_name=user.get("name", "User"))
    return {"message": "If this email is registered and unverified, a new verification link has been sent."}


