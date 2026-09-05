import asyncio
import os
import uuid

from fastapi import HTTPException, UploadFile, status

from app.config.logger import logger
from app.config.settings import settings
from app.database.mongodb import get_database
from app.services.syllabus_service import save_syllabus
from app.services.text_extraction_service import extract_text_with_method
from app.utils.object_id import to_object_id
from app.utils.file_validation import validate_extension, validate_content_type, read_within_limit

# Store uploads under a canonical, absolute directory so we can guarantee
# every stored file resolves back inside it (path-traversal protection).
UPLOAD_FOLDER = os.path.abspath("app/uploads")

# Extension allow-list mapped to the exact MIME type the client must send.
# Only PDF and DOCX are supported by the current system.
ALLOWED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    ),
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

# File validation moved to app.utils.file_validation


def _remove_file_quietly(filepath: str | None) -> None:
    """Best-effort cleanup of a partially/temporarily stored file."""
    if not filepath:
        return
    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
    except OSError:
        logger.exception("Failed to remove orphaned upload: %s", filepath)


async def save_uploaded_file(
    course_id: str,
    file: UploadFile,
) -> dict:
    db = get_database()

    # 1. Validate the course reference BEFORE writing anything to disk so a
    #    bad request never leaves an orphaned upload behind.
    course_oid = to_object_id(course_id, field="course_id")  # -> 400 if malformed

    course = await db.courses.find_one({"_id": course_oid})
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # 2. Validate extension + MIME before reading the body.
    original_filename = file.filename
    ext = validate_extension(original_filename, ALLOWED_TYPES)
    validate_content_type(ext, file.content_type, ALLOWED_TYPES)

    # 3. Read the body enforcing the size limit.
    contents = await read_within_limit(file)

    # 4. Generate a safe UUID filename; the original name is metadata only.
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, stored_filename)

    # Defense-in-depth: ensure the resolved path stays inside UPLOAD_FOLDER.
    resolved = os.path.abspath(filepath)
    if os.path.commonpath([resolved, UPLOAD_FOLDER]) != UPLOAD_FOLDER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path.",
        )

    # 5. Write, then extract. If anything fails after the file is written,
    #    remove it and do NOT create a partial MongoDB document.
    try:
        with open(resolved, "wb") as buffer:
            buffer.write(contents)

        # PDF/DOCX parsing (PyMuPDF/python-docx) and any OCR fallback are
        # blocking and CPU-heavy. Offload to a worker thread so uploads by one
        # faculty user never stall the event loop for others (Task #15).
        extracted_text, extraction_method = await asyncio.to_thread(
            extract_text_with_method, resolved
        )

        syllabus_id = await save_syllabus(
            course_id=course_oid,
            filename=stored_filename,
            filepath=resolved,
            extracted_text=extracted_text,
            original_filename=original_filename,
            extraction_method=extraction_method,
        )
    except HTTPException:
        # Controlled client errors (e.g. corrupted document) -> clean up.
        _remove_file_quietly(resolved)
        raise
    except Exception:
        # Unexpected failure -> clean up and let the global handler return a
        # safe 500 (internal details are logged, never returned).
        _remove_file_quietly(resolved)
        logger.exception("Unexpected error while saving uploaded syllabus")
        raise

    return {
        "syllabus_id": syllabus_id,
        "course_id": str(course_oid),
        "filename": original_filename,  # original name for display
        "stored_filename": stored_filename,
        "message": "Syllabus uploaded successfully",
    }
