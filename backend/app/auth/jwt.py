from datetime import datetime, timedelta, UTC

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config.settings import settings


def create_access_token(data: dict):
    payload = data.copy()

    expire = datetime.now(UTC) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload.update({"exp": expire})

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


# auto_error=False so a MISSING Authorization header does not trigger
# HTTPBearer's built-in 403. We handle the missing-credential case ourselves
# and return 401, as required for unauthenticated requests.
security = HTTPBearer(auto_error=False)


def verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = None
    if credentials:
        token = credentials.credentials
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        return payload

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )


def create_reset_token(email: str):
    expire = datetime.now(UTC) + timedelta(minutes=15)
    payload = {"sub": email, "type": "reset", "exp": expire}
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def verify_reset_token(token: str):
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "reset":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def create_email_verification_token(email: str) -> str:
    """Create a 24-hour email verification JWT."""
    expire = datetime.now(UTC) + timedelta(hours=24)
    payload = {"sub": email.lower(), "type": "email_verify", "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_email_token(token: str) -> str | None:
    """Verify the email confirmation token and return the email address, or None on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "email_verify":
            return None
        return payload.get("sub")
    except JWTError:
        return None

