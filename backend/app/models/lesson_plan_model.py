from datetime import datetime, UTC


def create_lesson_plan_document(
    filename: str,
    filepath: str,
    extracted_text: str,
    lesson_plan: str,
):
    return {
        "filename": filename,
        "filepath": filepath,
        "extracted_text": extracted_text,
        "lesson_plan": lesson_plan,
        "created_at": datetime.now(UTC),
    }