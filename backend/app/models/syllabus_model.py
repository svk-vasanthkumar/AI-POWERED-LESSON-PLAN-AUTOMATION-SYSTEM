from datetime import datetime, UTC

from bson import ObjectId


def create_syllabus_document(
    course_id: ObjectId,
    filename: str,
    filepath: str,
    extracted_text: str,
    original_filename: str | None = None,
    extraction_method: str = "text",
) -> dict:
    """Creates a standardized dictionary structure for MongoDB syllabus insertion.

    ``course_id`` is stored as a MongoDB ObjectId so it references
    ``courses._id`` natively (not as a string).

    ``filename`` is the safe, generated on-disk name (a UUID + extension).
    ``original_filename`` is the untrusted client-supplied name kept only as
    display metadata; it is never used to build a filesystem path.

    ``extraction_method`` records how ``text`` was obtained: ``"text"`` for a
    native text layer / DOCX, or ``"ocr"`` for a scanned PDF recognised via
    OCR. It is metadata only — the extracted text itself is never duplicated.
    """
    return {
        "course_id": course_id,
        "filename": filename,
        "filepath": filepath,
        "original_filename": original_filename,
        "text": extracted_text,
        "extraction_method": extraction_method,
        "created_at": datetime.now(UTC),
    }
