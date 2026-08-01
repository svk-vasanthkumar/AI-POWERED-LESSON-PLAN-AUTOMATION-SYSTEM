from datetime import datetime, UTC


def create_syllabus_document(
    course_id: str,
    filename: str,
    filepath: str,
    extracted_text: str,
) -> dict:
    """Creates a standardized dictionary structure for MongoDB syllabus insertion."""
    return {
        "course_id": course_id,
        "filename": filename,
        "filepath": filepath,
        "text": extracted_text,
        "created_at": datetime.now(UTC),
    }