from datetime import datetime, UTC


def create_syllabus_document(
    filename: str,
    filepath: str,
    extracted_text: str,
):
    return {
        "filename": filename,
        "filepath": filepath,
        "text": extracted_text,
        "created_at": datetime.now(UTC),
    }