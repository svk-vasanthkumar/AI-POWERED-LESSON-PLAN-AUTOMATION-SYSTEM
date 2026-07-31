from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.database.mongodb import get_database
from app.models.user_model import create_user_document
from app.schemas.user_schema import UserRegister


async def register_user(user: UserRegister):
    db = get_database()

    existing_user = await db.users.find_one(
        {"email": user.email.lower()}
    )

    if existing_user:
        raise ValueError("Email already registered")

    user_document = create_user_document(
        name=user.name,
        email=user.email,
        password=hash_password(user.password),
        role=user.role,
        department=user.department,
    )

    result = await db.users.insert_one(user_document)

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

    return {
        "access_token": token,
        "token_type": "bearer",
    }