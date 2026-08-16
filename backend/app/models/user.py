from datetime import datetime, timezone
from enum import Enum

from bson import ObjectId


class UserRole(str, Enum):
    ADMIN = "admin"
    HOD = "hod"
    FACULTY = "faculty"


def create_user_document(
    name: str,
    email: str,
    password_hash: str,
    role: UserRole,
    department: str,
):
    return {
        "_id": ObjectId(),
        "name": name.strip(),
        "email": email.strip().lower(),
        "password_hash": password_hash,
        "role": role.value,
        "department": department.strip(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }