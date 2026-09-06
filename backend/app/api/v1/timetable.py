from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks

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
    process_timetable_ocr,
)
import os
import uuid
from app.utils.file_validation import validate_extension, validate_content_type, read_within_limit
from app.utils.object_id import to_object_id

UPLOAD_FOLDER = os.path.abspath("app/uploads")
ALLOWED_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

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


@router.post(
    "/upload",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def upload_timetable(
    faculty_id: str,
    course_id: str,
    semester: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """Upload a timetable image and queue it for OCR processing."""
    # 1. Validate extension + MIME
    original_filename = file.filename
    ext = validate_extension(original_filename, ALLOWED_TYPES)
    validate_content_type(ext, file.content_type, ALLOWED_TYPES)
    
    # 2. Read the body enforcing the size limit
    contents = await read_within_limit(file)
    
    # 3. Save to disk
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, stored_filename)
    
    with open(filepath, "wb") as buffer:
        buffer.write(contents)
        
    # 4. Create document in processing state
    db = get_database()
    faculty_oid = to_object_id(faculty_id, field="faculty_id")
    course_oid = to_object_id(course_id, field="course_id")
    
    from app.models.timetable_model import create_timetable_document
    document = create_timetable_document(
        faculty_id=faculty_oid,
        course_id=course_oid,
        semester=semester,
        schedule=[],
        status="OCR_PENDING",
        original_filename=original_filename,
        stored_filename=stored_filename,
    )
    result = await db.timetables.insert_one(document)
    timetable_id = str(result.inserted_id)
    
    # 5. Kick off OCR in background
    background_tasks.add_task(process_timetable_ocr, timetable_id, filepath)
    
    return {
        "timetable_id": timetable_id,
        "message": "Timetable uploaded and queued for processing."
    }

@router.post(
    "/{timetable_id}/retry",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def retry_timetable_ocr(timetable_id: str, background_tasks: BackgroundTasks):
    """Retry OCR for a failed timetable upload."""
    db = get_database()
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        obj_id = ObjectId(timetable_id)
    except InvalidId:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Timetable not found")
        
    timetable = await db.timetables.find_one({"_id": obj_id})
    if not timetable:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Timetable not found")
        
    if timetable.get("status") not in ("REJECTED", "DRAFT"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Can only retry REJECTED or DRAFT timetables")
        
    stored_filename = timetable.get("stored_filename")
    if not stored_filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No stored image found to retry OCR")
        
    filepath = os.path.join(UPLOAD_FOLDER, stored_filename)
    if not os.path.exists(filepath):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Image file not found on disk")
        
    # Reset state to processing
    await db.timetables.update_one(
        {"_id": obj_id},
        {"$set": {"status": "OCR_PENDING"}}
    )
    
    # Queue task
    background_tasks.add_task(process_timetable_ocr, timetable_id, filepath)
    
    return {"message": "OCR retry queued."}


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
    dependencies=[Depends(require_roles("admin", "hod", "faculty"))],
)
async def remove_timetable(
    timetable_id: str,
    current_user: dict = Depends(get_current_user),
):
    timetable = await get_timetable(timetable_id)
    if not timetable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timetable not found",
        )

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
