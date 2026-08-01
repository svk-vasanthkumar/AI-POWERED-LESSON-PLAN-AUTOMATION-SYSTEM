import os
import uuid
from fastapi import UploadFile

from app.services.syllabus_service import save_syllabus
from app.services.text_extraction_service import extract_text

UPLOAD_FOLDER = "app/uploads"


async def save_uploaded_file(
    course_id: str,
    file: UploadFile,
) -> dict:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    extension = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{extension}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    with open(filepath, "wb") as buffer:
        buffer.write(await file.read())

    extracted_text = extract_text(filepath)

    syllabus_id = await save_syllabus(
        course_id=course_id,
        filename=filename,
        filepath=filepath,
        extracted_text=extracted_text,
    )

    return {
        "syllabus_id": syllabus_id,
        "course_id": course_id,
        "filename": filename,
        "filepath": filepath,
        "message": "Syllabus uploaded successfully",
    }