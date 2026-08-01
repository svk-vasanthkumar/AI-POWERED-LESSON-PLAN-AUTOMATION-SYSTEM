from fastapi import APIRouter, HTTPException

from app.schemas.faculty_schema import FacultyCreate
from app.services.faculty_service import (
    create_faculty,
    get_all_faculty,
    get_faculty,
)

router = APIRouter(
    prefix="/faculty",
    tags=["Faculty"],
)


@router.post("/")
async def add_faculty(data: FacultyCreate):
    try:
        faculty_id = await create_faculty(data)

        return {
            "faculty_id": faculty_id,
            "message": "Faculty created successfully",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.get("/")
async def list_faculty():
    return await get_all_faculty()


@router.get("/{faculty_id}")
async def single_faculty(faculty_id: str):
    faculty = await get_faculty(faculty_id)

    if not faculty:
        raise HTTPException(
            status_code=404,
            detail="Faculty not found",
        )

    return faculty