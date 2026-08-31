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
    )

    try:
        result = await db.users.insert_one(user_document)
    except DuplicateKeyError:
        # Unique index on users.email raced with the pre-check above; return a
        # controlled 400 instead of an unhandled 500.
        raise ValueError("Email already registered")

    return {
        "message": "User registered successfully",
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


async def update_user_profile(email: str, name: str, department: str):
    db = get_database()
    user = await db.users.find_one({"email": email})
    
    if not user:
        raise ValueError("User not found")
        
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"name": name, "department": department}}
    )
    return {"message": "Profile updated successfully"}


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
