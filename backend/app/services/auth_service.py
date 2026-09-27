from pymongo.errors import DuplicateKeyError

from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.database.mongodb import get_database
from app.models.user_model import create_user_document
from app.schemas.user_schema import UserRegister


async def register_user(user: UserRegister):
    db = get_database()

    # This is the public registration flow.  Privileged accounts must never be
    # created from a value supplied by an unauthenticated client.
    if user.role != "faculty":
        raise ValueError("Public registration can only create faculty users")

    existing_user = await db.users.find_one(
        {"email": user.email.lower()}
    )

    if existing_user:
        raise ValueError("Email already registered")

    user_document = create_user_document(
        name=user.name,
        email=user.email,
        password=hash_password(user.password),
        role="faculty",
        department=user.department,
        is_email_verified=False,  # Must verify via email link
    )

    try:
        result = await db.users.insert_one(user_document)
    except DuplicateKeyError:
        raise ValueError("Email already registered")

    # Send verification email asynchronously (non-blocking)
    try:
        from app.auth.jwt import create_email_verification_token
        from app.services.email_service import send_verification_email
        token = create_email_verification_token(user.email)
        send_verification_email(user.email, token, user_name=user.name)
    except Exception:
        pass  # Never block registration if email fails

    return {
        "message": "Registration successful! Please check your email to verify your account before logging in.",
        "user_id": str(result.inserted_id),
    }


async def login_user(email: str, password: str):
    db = get_database()

    user = await db.users.find_one(
        {"email": email.lower()}
    )

    if not user:
        raise ValueError("Invalid email or password")

    if not verify_password(password, user["password"]):
        raise ValueError("Invalid email or password")

    # Block local accounts that have not verified their email.
    # Admin-created users (is_email_verified=True) are exempt.
    if not user.get("is_email_verified", True):
        raise ValueError(
            "EMAIL_NOT_VERIFIED:Please verify your email address before logging in. "
            "Check your inbox for the verification link."
        )

    token = create_access_token(
        {
            "sub": str(user["_id"]),
            "role": user["role"],
            "email": user["email"],
        }
    )

    if not user.get("has_logged_in"):
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"has_logged_in": True}}
        )

    return {
        "access_token": token,
        "token_type": "bearer",
    }


async def reset_password(email: str, current_password: str, new_password: str):
    db = get_database()

    user = await db.users.find_one({"email": email.lower()})

    if not user:
        raise ValueError("Invalid email or current password")

    if not verify_password(current_password, user["password"]):
        raise ValueError("Invalid email or current password")

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password": hash_password(new_password)}}
    )

    return {"message": "Password changed successfully"}


async def handle_forgot_password(email: str):
    db = get_database()
    user = await db.users.find_one({"email": email.lower()})
    
    # Do nothing if user doesn't exist (prevents email enumeration)
    if not user:
        return
        
    from app.auth.jwt import create_reset_token
    from app.services.email_service import send_password_reset_email
    
    token = create_reset_token(email.lower())
    send_password_reset_email(email.lower(), token)


async def handle_reset_password_token(token: str, new_password: str):
    from app.auth.jwt import verify_reset_token
    
    email = verify_reset_token(token)
    if not email:
        raise ValueError("Invalid or expired reset token")
        
    db = get_database()
    user = await db.users.find_one({"email": email})
    
    if not user:
        raise ValueError("User not found")
        
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password": hash_password(new_password)}}
    )
    
    from app.services.email_service import send_security_alert_email
    send_security_alert_email(email)


async def update_user_profile(
    current_email: str,
    name: str,
    department: str | None = None,
    new_email: str | None = None,
    role: str = "faculty",
):
    db = get_database()
    user = await db.users.find_one({"email": current_email.lower()})

    if not user:
        raise ValueError("User not found")

    set_fields: dict = {"name": name}

    # Admin-only: allow department change
    if role == "admin" and department:
        set_fields["department"] = department

    # Admin-only: allow email change
    email_changed = False
    resolved_email = current_email.lower()
    if role == "admin" and new_email and new_email.lower() != current_email.lower():
        existing = await db.users.find_one({"email": new_email.lower()})
        if existing:
            raise ValueError("That email address is already registered to another account.")
        set_fields["email"] = new_email.lower()
        email_changed = True
        resolved_email = new_email.lower()

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": set_fields}
    )

    # Sync name/email to faculty collection if a faculty document exists
    faculty_set = {k: v for k, v in set_fields.items() if k in ("name", "email")}
    if faculty_set:
        await db.faculty.update_many(
            {"$or": [
                {"user_id": str(user["_id"])},
                {"user_id": user["_id"]},
                {"email": current_email.lower()},
            ]},
            {"$set": faculty_set}
        )

    return {
        "message": "Profile updated successfully",
        "email_changed": email_changed,
        "new_email": resolved_email,
    }



async def update_user_preferences(email: str, preferences: dict):
    db = get_database()
    user = await db.users.find_one({"email": email})
    
    if not user:
        raise ValueError("User not found")
        
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"preferences": preferences}}
    )
    return {"message": "Preferences updated successfully"}

async def add_push_subscription(email: str, subscription: dict):
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        raise ValueError("User not found")
    
    # We maintain an array of push_subscriptions, avoiding duplicates by endpoint
    subs = user.get("push_subscriptions", [])
    exists = False
    for sub in subs:
        if sub.get("endpoint") == subscription.get("endpoint"):
            # Update keys if endpoint exists
            sub["keys"] = subscription.get("keys")
            sub["expirationTime"] = subscription.get("expirationTime")
            exists = True
            break
            
    if not exists:
        subs.append(subscription)
        
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"push_subscriptions": subs}}
    )
    return {"message": "Push subscription added"}


async def verify_email_token_service(token: str) -> dict:
    """Verify the email confirmation token and mark the user as verified."""
    from app.auth.jwt import verify_email_token

    email = verify_email_token(token)
    if not email:
        raise ValueError("Invalid or expired verification link. Please request a new one.")

    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        raise ValueError("Account not found.")

    if user.get("is_email_verified"):
        return {"message": "Your email is already verified. You can now log in."}

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"is_email_verified": True}}
    )
    return {"message": "Email verified successfully! You can now log in."}


