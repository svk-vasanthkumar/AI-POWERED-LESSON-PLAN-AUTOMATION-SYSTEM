from fastapi import APIRouter, File, Form, UploadFile

from app.services.upload_service import save_uploaded_file

router = APIRouter(
    prefix="/syllabus",
    tags=["Syllabus"],
)


@router.post("/upload")
async def upload_syllabus(
    course_id: str = Form(...),
    file: UploadFile = File(...),
):
    return await save_uploaded_file(
        course_id=course_id,
        file=file,
    )