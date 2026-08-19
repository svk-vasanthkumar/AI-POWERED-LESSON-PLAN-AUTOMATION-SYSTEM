from datetime import datetime, UTC


def create_user_document(
    name: str,
    email: str,
    password: str,
    role: str,
    department: str,
):
    return {
        "name": name,
        "email": email.lower(),
        "password": password,
        "role": role,
        "department": department,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }