from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_roles
from app.auth.resource_access import (
    ids_match,
    is_manager,
    faculty_object_id_for_user,
)
from app.database.mongodb import get_database
from app.schemas.timetable_schema import TimetableCreate, TimetableUpdate
from app.services.timetable_service import (
    TimetableInUseError,
    create_timetable,
    delete_timetable,
    get_all_timetables,
    get_timetable,
    update_timetable,
)

# Every timetable endpoint requires a valid Bearer JWT.
router = APIRouter(
    prefix="/timetable",
    tags=["Timetable"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def add_timetable(data: TimetableCreate):
    try:
        timetable_id = await create_timetable(data)

        return {
            "timetable_id": timetable_id,
            "message": "Timetable created successfully",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/")
async def list_timetables(current_user: dict = Depends(get_current_user)):
    """List timetables.

    admin/hod see every timetable; faculty see only their own timetables
    (matched on ``timetables.faculty_id`` -> ``faculty._id``).
    """
    timetables = await get_all_timetables()
    if is_manager(current_user):
        return timetables

    db = get_database()
    faculty_oid = await faculty_object_id_for_user(db, current_user)
    if faculty_oid is None:
        return []
    return [t for t in timetables if ids_match(t.get("faculty_id"), faculty_oid)]


@router.get("/{timetable_id}")
async def single_timetable(
    timetable_id: str,
    current_user: dict = Depends(get_current_user),
):
    timetable = await get_timetable(timetable_id)
    if not timetable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timetable not found",
        )

    # Faculty may only read their own timetable information.
    if not is_manager(current_user):
        db = get_database()
        faculty_oid = await faculty_object_id_for_user(db, current_user)
        if faculty_oid is None or not ids_match(
            timetable.get("faculty_id"), faculty_oid
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
    return timetable


@router.put(
    "/{timetable_id}",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def edit_timetable(timetable_id: str, data: TimetableUpdate):
    try:
        updated = await update_timetable(timetable_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if updated == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timetable not found or no changes applied",
        )

    return {"message": "Timetable updated successfully"}


@router.delete(
    "/{timetable_id}",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def remove_timetable(timetable_id: str):
    try:
        deleted = await delete_timetable(timetable_id)
    except TimetableInUseError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timetable not found",
        )

    return {"message": "Timetable deleted successfully"}
