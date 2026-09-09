from datetime import datetime, UTC


def create_user_document(
    name: str,
    email: str,
    password: str,
    role: str,
    department: str,
    is_email_verified: bool = False,
):
    """
    Create a new user document for MongoDB.

    is_email_verified:
      - False  → standard self-registration; user must click email link
      - True   → admin-created accounts (pre-verified by the admin)
    """
    doc = {
        "name": name,
        "email": email.lower(),
        "password": password,
        "role": role,
        "department": department,
        "has_logged_in": False,
        "is_email_verified": is_email_verified,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    return doc