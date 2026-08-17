import asyncio
import getpass

from app.database import db
from app.models.user import create_user_document, UserRole
from app.utils.password import hash_password


async def main():
    print("Create Admin / HOD")

    name = input("Name: ").strip()
    email = input("Email: ").strip().lower()
    department = input("Department: ").strip()

    role = input("Role (admin/hod): ").strip().lower()

    if role not in {"admin", "hod"}:
        print("Role must be admin or hod")
        return

    password = getpass.getpass("Password: ")

    existing = await db.users.find_one(
        {"email": email}
    )

    if existing:
        print("User already exists")
        return

    user = create_user_document(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=UserRole(role),
        department=department,
    )

    await db.users.insert_one(user)

    print("Management user created")
    print("ID:", user["_id"])
    print("Role:", role)


if __name__ == "__main__":
    asyncio.run(main())