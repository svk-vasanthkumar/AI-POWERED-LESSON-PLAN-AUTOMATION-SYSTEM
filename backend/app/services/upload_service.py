import os
import uuid
from fastapi import UploadFile

from app.services.text_extraction_service import extract_text

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

    return {
        "filename": filename,
        "filepath": filepath,
        "text": extracted_text,
    }