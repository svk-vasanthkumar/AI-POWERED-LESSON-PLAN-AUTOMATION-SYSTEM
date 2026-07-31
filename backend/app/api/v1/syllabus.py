from fastapi import APIRouter, UploadFile, File

from app.services.upload_service import save_uploaded_file

router = APIRouter(
    prefix="/syllabus",
    tags=["Syllabus"],
)


@router.post("/upload")
async def upload_syllabus(
    file: UploadFile = File(...)
):
    return await save_uploaded_file(file)