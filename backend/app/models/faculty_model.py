from datetime import UTC, datetime


def create_faculty_document(
    user_id,
    faculty_id: str,
    name: str,
    email: str,
    department: str,
    designation: str,
) -> dict:
    """Creates a standardized dictionary structure for MongoDB insertion."""
    return {
        "user_id": user_id,
        "faculty_id": faculty_id.strip(),
        "name": name.strip(),
        "email": email.lower().strip(),
        "department": department.strip(),
        "designation": designation.strip(),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }