from fastapi import APIRouter, HTTPException

from app.schemas.course_schema import CourseCreate
from app.services.course_service import create_course

router = APIRouter(
    prefix="/course",
    tags=["Course"],
)


@router.post("/")
async def add_course(data: CourseCreate):
    try:
        course_id = await create_course(data)

        return {
            "course_id": course_id,
            "message": "Course created successfully",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )