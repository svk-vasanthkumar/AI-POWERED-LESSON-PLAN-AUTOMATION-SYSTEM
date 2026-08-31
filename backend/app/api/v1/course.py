from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_roles
from app.auth.resource_access import (
    accessible_course_ids,
    ensure_course_access,
)
from app.database.mongodb import get_database
from app.schemas.course_schema import CourseCreate, CourseUpdate
from app.services.course_service import (
    CourseInUseError,
    create_course,
    delete_course,
    get_all_courses,
    get_course,
    update_course,
    clone_course,
)
from pydantic import BaseModel, Field

class CourseCloneRequest(BaseModel):
    new_faculty_id: str = Field(..., description="The ID of the new faculty member to assign")
    new_academic_year: str = Field(..., description="The new academic year (e.g. 2026-2027)")

# Every course endpoint requires a valid Bearer JWT.
router = APIRouter(
    prefix="/course",
    tags=["Course"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def add_course(data: CourseCreate):
    try:
        course_id = await create_course(data)

        return {
            "course_id": course_id,
            "message": "Course created successfully",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/")
async def list_courses(current_user: dict = Depends(get_current_user)):
    """List courses.

    admin/hod see every course; faculty see only the courses assigned to them
    via the ``courses.faculty_id`` -> ``faculty._id`` relationship.
    """
    db = get_database()
    course_ids = await accessible_course_ids(db, current_user)
    return await get_all_courses(course_ids)


@router.get("/{course_id}")
async def single_course(
    course_id: str,
    current_user: dict = Depends(get_current_user),
):
    course = await get_course(course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # Faculty may only read courses they are authorized to access.
    db = get_database()
    await ensure_course_access(db, current_user, course)
    return course


@router.put(
    "/{course_id}",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def edit_course(course_id: str, data: CourseUpdate):
    try:
        updated = await update_course(course_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if updated == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    return {"message": "Course updated successfully"}


@router.delete(
    "/{course_id}",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def remove_course(course_id: str):
    try:
        deleted = await delete_course(course_id)
    except CourseInUseError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    return {"message": "Course deleted successfully"}


@router.post(
    "/{course_id}/clone",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def clone_existing_course(course_id: str, data: CourseCloneRequest):
    """Clone an existing course, its syllabus, and lesson plan for reuse."""
    try:
        new_course_id = await clone_course(course_id, data.new_faculty_id, data.new_academic_year)
        return {
            "course_id": new_course_id,
            "message": "Course cloned successfully",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
