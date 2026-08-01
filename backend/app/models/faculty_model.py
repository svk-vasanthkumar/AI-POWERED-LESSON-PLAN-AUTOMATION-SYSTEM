from datetime import datetime, UTC


def create_faculty_document(
    faculty_id: str,
    name: str,
    email: str,
    department: str,
    designation: str,
):
    return {
        "faculty_id": faculty_id,
        "name": name,
        "email": email.lower(),
        "department": department,
        "designation": designation,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }