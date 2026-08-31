from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_roles
from app.schemas.faculty_schema import FacultyCreate, FacultyUpdate, EmailCredentials
from app.services.faculty_service import (
    FacultyInUseError,
    create_faculty,
    delete_faculty,
    get_all_faculty,
    get_faculty,
    update_faculty,
    send_welcome_email,
)

# Every faculty endpoint requires a valid Bearer JWT.
router = APIRouter(
    prefix="/faculty",
    tags=["Faculty"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin", "hod"))],
)
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


@router.put(
    "/{faculty_id}",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def edit_faculty(faculty_id: str, data: FacultyUpdate):
    try:
        updated = await update_faculty(faculty_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if updated == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found or no changes applied",
        )

    return {"message": "Faculty updated successfully"}


@router.delete(
    "/{faculty_id}",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def remove_faculty(faculty_id: str):
    try:
        deleted = await delete_faculty(faculty_id)
    except FacultyInUseError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found",
        )

    return {"message": "Faculty deleted successfully"}


@router.post(
    "/{faculty_id}/send-email",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def send_email(faculty_id: str, creds: EmailCredentials):
    success = await send_welcome_email(faculty_id, creds.password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )
    return {"message": "Email sent successfully"}
