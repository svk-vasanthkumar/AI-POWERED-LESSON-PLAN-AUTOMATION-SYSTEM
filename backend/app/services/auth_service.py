from app.database.mongodb import get_database
from app.models.user_model import create_user_document
from app.auth.password import hash_password
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