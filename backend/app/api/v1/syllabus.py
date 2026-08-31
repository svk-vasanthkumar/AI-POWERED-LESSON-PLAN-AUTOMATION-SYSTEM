from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.auth.dependencies import get_current_user, require_roles
from app.auth.resource_access import accessible_course_ids, ensure_course_access
from app.database.mongodb import get_database
from app.services.syllabus_service import (
    SyllabusInUseError,
    delete_syllabus,
    get_all_syllabi,
    get_syllabus,
    get_syllabus_raw,
)
from app.services.upload_service import save_uploaded_file

# Every syllabus endpoint requires a valid Bearer JWT.
# All roles (admin, hod, faculty) may upload a syllabus.
router = APIRouter(
    prefix="/syllabus",
    tags=["Syllabus"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/upload")
async def upload_syllabus(
    course_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    # A faculty user may only upload a syllabus to a course they are assigned
    # to; admin/hod may upload to any course. ``save_uploaded_file`` validates
    # that the course exists (-> 404) before anything is written to disk.
    db = get_database()
    from app.auth.resource_access import ensure_course_id_access
    from app.utils.object_id import to_object_id

    await ensure_course_id_access(
        db, current_user, to_object_id(course_id, field="course_id")
    )

    return await save_uploaded_file(
        course_id=course_id,
        file=file,
    )


@router.get("/")
async def list_syllabi(
    course_id: str | None = Query(
        default=None,
        description="Optional course id to filter syllabi by course.",
    ),
    current_user: dict = Depends(get_current_user),
):
    """List syllabi.

    admin/hod see every syllabus; faculty see only syllabi belonging to courses
    they are authorized to access. An optional ``course_id`` filters further.
    """
    db = get_database()
    scope = await accessible_course_ids(db, current_user)
    return await get_all_syllabi(course_id=course_id, scope_course_ids=scope)


@router.get("/{syllabus_id}")
async def single_syllabus(
    syllabus_id: str,
    current_user: dict = Depends(get_current_user),
):
    syllabus = await get_syllabus(syllabus_id)
    if not syllabus:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Syllabus not found",
        )

    # Authorize via the syllabus's parent course (never expose another
    # department's syllabus just because the caller has a valid JWT).
    db = get_database()
    raw = await get_syllabus_raw(syllabus_id)
    course = await db.courses.find_one({"_id": raw.get("course_id")}) if raw else None
    if course is None:
        course = await db.courses.find_one({"_id": str(raw.get("course_id"))})
    await ensure_course_access(db, current_user, course)
    return syllabus


@router.delete(
    "/{syllabus_id}",
    dependencies=[Depends(require_roles("admin", "hod", "faculty"))],
)
async def remove_syllabus(
    syllabus_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = get_database()
    raw = await get_syllabus_raw(syllabus_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Syllabus not found")
        
    course = await db.courses.find_one({"_id": raw.get("course_id")})
    if course is None:
        course = await db.courses.find_one({"_id": str(raw.get("course_id"))})
        
    await ensure_course_access(db, current_user, course)
    
    try:
        deleted = await delete_syllabus(syllabus_id)
    except SyllabusInUseError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Syllabus not found",
        )

    return {"message": "Syllabus deleted successfully"}
