from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.dependencies import get_current_user, require_roles
from app.auth.resource_access import (
    accessible_course_ids,
    ids_match,
    is_manager,
)
from app.database.mongodb import get_database
from app.schemas.lesson_plan_schema import LessonPlanUpdate
from app.utils.object_id import to_object_id
from app.services.ai_service import AIGenerationError, AIServiceUnavailableError
from app.services.export_service import (
    DocumentGenerationError,
    LessonPlanNotFoundError,
    StructuredPlanRequiredError,
    build_lesson_plan_export,
)
from app.services.lesson_plan_service import (
    LessonPlanInUseError,
    delete_lesson_plan,
    generate_and_save_lesson_plan,
)

# Every lesson-plan endpoint requires a valid Bearer JWT.
router = APIRouter(
    prefix="/lesson-plan",
    tags=["Lesson Plan"],
    dependencies=[Depends(get_current_user)],
)


def _serialize_lesson(lesson: dict) -> dict:
    """Stringify ObjectId fields for a JSON-safe response."""
    lesson["_id"] = str(lesson["_id"])
    if "syllabus_id" in lesson:
        lesson["syllabus_id"] = str(lesson["syllabus_id"])
    if "course_id" in lesson:
        lesson["course_id"] = str(lesson["course_id"])
    return lesson


async def _load_authorized_lesson(lesson_id: str, current_user: dict) -> dict:
    """Fetch a lesson plan and enforce read/write ownership.

    Managers (admin/hod) may access any lesson plan. Faculty may only access
    lesson plans whose ``course_id`` belongs to a course they own (the Task #2
    ``courses.faculty_id`` -> ``faculty._id`` relationship, resolved to the
    caller via their linked faculty record). A malformed or unknown id returns
    404; an existing-but-unowned plan returns 403.
    """
    db = get_database()

    # A malformed id is a client error (400), consistent with the rest of the
    # codebase (``to_object_id``) and with the documented export contract. The
    # authorization wrapper must not silently downgrade that to a 404.
    obj_id = to_object_id(lesson_id, field="lesson_id")

    lesson = await db.lesson_plans.find_one({"_id": obj_id})
    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson plan not found",
        )

    if not is_manager(current_user):
        allowed = await accessible_course_ids(db, current_user)
        allowed = allowed or []
        if not any(ids_match(lesson.get("course_id"), cid) for cid in allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )

    return lesson


@router.post("/generate/{syllabus_id}")
async def generate(syllabus_id: str):
    try:
        return await generate_and_save_lesson_plan(syllabus_id)
    except AIServiceUnavailableError as e:
        # The Groq provider itself could not be reached / failed (network,
        # timeout, auth, rate-limit, 5xx). Surface a safe 503 so callers can
        # retry; provider internals are never leaked.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except AIGenerationError as e:
        # The model responded but failed to return usable structured output
        # (empty/malformed JSON or schema validation failure). Surface a safe
        # 502 (bad upstream) rather than a misleading 404.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/")
async def get_all_lesson_plans(current_user: dict = Depends(get_current_user)):
    """List lesson plans scoped to the caller.

    admin/hod see every lesson plan; faculty see only lesson plans for courses
    they own.
    """
    db = get_database()

    allowed = await accessible_course_ids(db, current_user)

    query: dict = {}
    if allowed is not None:
        if not allowed:
            return []
        # Match either ObjectId or legacy string course references.
        variants: list = []
        for cid in allowed:
            variants.append(cid)
            variants.append(str(cid))
        query = {"course_id": {"$in": variants}}

    lesson_plans = []
    async for lesson in db.lesson_plans.find(query):
        lesson_plans.append(_serialize_lesson(lesson))

    return lesson_plans


@router.get("/{lesson_id}")
async def get_lesson_plan(
    lesson_id: str,
    current_user: dict = Depends(get_current_user),
):
    lesson = await _load_authorized_lesson(lesson_id, current_user)
    return _serialize_lesson(lesson)


@router.put("/{lesson_id}")
async def update_lesson_plan(
    lesson_id: str,
    data: LessonPlanUpdate,
    current_user: dict = Depends(get_current_user),
):
    # Ownership is enforced here: faculty may only edit lesson plans for their
    # own courses; managers may edit any.
    lesson = await _load_authorized_lesson(lesson_id, current_user)

    db = get_database()
    await db.lesson_plans.update_one(
        {"_id": lesson["_id"]},
        {"$set": {"lesson_plan": data.lesson_plan}},
    )

    return {"message": "Lesson plan updated successfully"}


@router.delete(
    "/{lesson_id}",
    dependencies=[Depends(require_roles("admin", "hod"))],
)
async def remove_lesson_plan(lesson_id: str):
    try:
        deleted = await delete_lesson_plan(lesson_id)
    except LessonPlanInUseError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson plan not found",
        )

    return {"message": "Lesson plan deleted successfully"}


# ---------------------------------------------------------------------------
# Deterministic exports (PDF / DOCX / XLSX)
#
# These reuse the router-level JWT dependency (``get_current_user``) so every
# export requires a valid Bearer token — there are no public export endpoints.
# Documents are built from stored MongoDB data only (no LLM involvement).
#
# Access is additionally scoped: faculty may only export lesson plans for
# courses they own (``_load_authorized_lesson``), managers may export any.
#
# Controlled error mapping (Phase 11):
#     400  malformed ObjectId          (raised by ``to_object_id``)
#     404  lesson plan not found        (LessonPlanNotFoundError)
#     422  structured plan missing      (StructuredPlanRequiredError)
#     500  document generation failure  (DocumentGenerationError; internals
#          are logged server-side and never surfaced to the client)
# ---------------------------------------------------------------------------


async def _export_lesson_plan_response(lesson_plan_id: str, fmt: str) -> Response:
    try:
        content, filename, media_type = await build_lesson_plan_export(
            lesson_plan_id, fmt
        )
    except LessonPlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except StructuredPlanRequiredError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except DocumentGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{lesson_plan_id}/export/pdf")
async def export_lesson_plan_as_pdf(
    lesson_plan_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _load_authorized_lesson(lesson_plan_id, current_user)
    return await _export_lesson_plan_response(lesson_plan_id, "pdf")


@router.get("/{lesson_plan_id}/export/docx")
async def export_lesson_plan_as_docx(
    lesson_plan_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _load_authorized_lesson(lesson_plan_id, current_user)
    return await _export_lesson_plan_response(lesson_plan_id, "docx")


@router.get("/{lesson_plan_id}/export/xlsx")
async def export_lesson_plan_as_xlsx(
    lesson_plan_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _load_authorized_lesson(lesson_plan_id, current_user)
    return await _export_lesson_plan_response(lesson_plan_id, "xlsx")
