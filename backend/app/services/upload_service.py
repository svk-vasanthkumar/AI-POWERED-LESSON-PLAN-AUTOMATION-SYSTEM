import os
import uuid
from fastapi import UploadFile

from app.services.text_extraction_service import extract_text
from app.services.ai_service import generate_lesson_plan
from app.services.lesson_plan_service import save_lesson_plan


UPLOAD_FOLDER = "app/uploads"


async def save_uploaded_file(file: UploadFile):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    extension = file.filename.split(".")[-1]

    filename = f"{uuid.uuid4()}.{extension}"

    filepath = os.path.join(
        UPLOAD_FOLDER,
        filename,
    )

    with open(filepath, "wb") as buffer:
        buffer.write(await file.read())

    extracted_text = extract_text(filepath)

    lesson_plan = await generate_lesson_plan(extracted_text)

    lesson_plan_id = await save_lesson_plan(
        filename,
        filepath,
        extracted_text,
        lesson_plan,
    )

    return {
        "lesson_plan_id": lesson_plan_id,
        "filename": filename,
        "lesson_plan": lesson_plan,
    }