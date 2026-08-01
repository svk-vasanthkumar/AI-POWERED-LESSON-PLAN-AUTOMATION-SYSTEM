from fastapi import APIRouter, HTTPException, status

from app.schemas.faculty_schema import FacultyCreate, FacultyUpdate
from app.services.faculty_service import (
    create_faculty,
    delete_faculty,
    get_all_faculty,
    get_faculty,
    update_faculty,
)

router = APIRouter(
    prefix="/faculty",
    tags=["Faculty"],
)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_faculty(data: FacultyCreate):
    try:
        faculty_id = await create_faculty(data)
        return {
            "faculty_id": faculty_id,
            "message": "Faculty created successfully",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found",
        )
    return faculty


@router.put("/{faculty_id}")
async def edit_faculty(faculty_id: str, data: FacultyUpdate):
    updated = await update_faculty(faculty_id, data)

    if updated == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found or no changes applied",
        )

    return {"message": "Faculty updated successfully"}


@router.delete("/{faculty_id}")
async def remove_faculty(faculty_id: str):
    deleted = await delete_faculty(faculty_id)

    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found",
        )

    return {"message": "Faculty deleted successfully"}