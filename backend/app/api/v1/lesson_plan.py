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
    """Stringify ObjectId fields and normalize missing fields for a JSON-safe response."""
    lesson["_id"] = str(lesson["_id"])
    if "syllabus_id" in lesson:
        lesson["syllabus_id"] = str(lesson["syllabus_id"])
    if "course_id" in lesson:
        lesson["course_id"] = str(lesson["course_id"])
    # Normalize status so the frontend always has a valid string
    if not lesson.get("status"):
        lesson["status"] = "Draft"
    # Serialize datetime fields to ISO strings
    for field in ("created_at", "updated_at"):
        val = lesson.get(field)
        if val is not None and hasattr(val, "isoformat"):
            lesson[field] = val.isoformat()
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
    update_data = {}
    if data.lesson_plan is not None:
        update_data["lesson_plan"] = data.lesson_plan
    if data.sessions is not None:
        update_data["sessions"] = data.sessions
    if data.approval_remarks is not None:
        update_data["approval_remarks"] = data.approval_remarks

    # Validate remarks for Approve/Reject
    if data.status in ["Approved", "Rejected"]:
        if not data.approval_remarks and not lesson.get("approval_remarks"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approval remarks are compulsory when approving or rejecting a lesson plan."
            )

    if data.status is not None:
        update_data["status"] = data.status

    if update_data:
        await db.lesson_plans.update_one(
            {"_id": lesson["_id"]},
            {"$set": update_data},
        )
        
        old_status = lesson.get("status")
        
        # Targeted Notifications
        from app.services.notification_service import dispatch_targeted_notification, resolve_course_recipients, resolve_department_hod
        
        course_id_str = str(lesson.get("course_id", ""))
        course = await db.courses.find_one({"_id": lesson.get("course_id")})
        if not course and course_id_str:
            course = await db.courses.find_one({"id": course_id_str})
            
        course_code = course.get("course_code", "Course") if course else "Course"
        course_name = course.get("course_name", "") if course else ""

        # 1. When faculty submits for approval -> Notify Department HOD
        if data.status == "Pending Approval" and data.status != old_status:
            dept = course.get("department") if course else current_user.get("department")
            hod_recipients = await resolve_department_hod(dept, exclude_user_id=current_user["id"])
            for hod_uid in hod_recipients:
                await dispatch_targeted_notification(
                    recipient_id=hod_uid,
                    actor_id=current_user["id"],
                    actor_name=current_user.get("name", "Faculty"),
                    event_type="LESSON_PLAN_SUBMITTED",
                    entity_type="LESSON_PLAN",
                    entity_id=lesson_id,
                    course_id=course_id_str,
                    severity="INFO",
                    type="info",
                    title="Lesson Plan Pending Approval",
                    message=f"A lesson plan for {course_code} ({course_name}) has been submitted for approval by {current_user.get('name', 'Faculty')}.",
                    link=f"/lesson-plans/edit/{lesson_id}",
                    email_subject=f"Lesson Plan Pending Approval: {course_code}",
                    metadata={
                        "course_code": course_code,
                        "course_name": course_name,
                        "submitted_by": current_user.get("name", "Faculty"),
                        "status": "Pending Approval"
                    }
                )
                
        # 2. When HOD approves or rejects -> Notify Faculty Owner(s)
        elif data.status in ["Approved", "Rejected"] and data.status != old_status:
            course_recipients = await resolve_course_recipients(course_id_str, exclude_user_id=current_user["id"])
            for fac_uid in course_recipients:
                await dispatch_targeted_notification(
                    recipient_id=fac_uid,
                    actor_id=current_user["id"],
                    actor_name=current_user.get("name", "HOD"),
                    event_type=f"LESSON_PLAN_{data.status.upper()}",
                    entity_type="LESSON_PLAN",
                    entity_id=lesson_id,
                    course_id=course_id_str,
                    severity="SUCCESS" if data.status == "Approved" else "ERROR",
                    type="success" if data.status == "Approved" else "warning",
                    title=f"Lesson Plan {data.status}",
                    message=f"Your lesson plan for {course_code} ({course_name}) has been {data.status.lower()} by {current_user.get('name', 'HOD')}.\nRemarks: {data.approval_remarks}",
                    link=f"/lesson-plans/edit/{lesson_id}",
                    email_subject=f"Lesson Plan {data.status}: {course_code}",
                    metadata={
                        "course_code": course_code,
                        "course_name": course_name,
                        "status": data.status,
                        "approval_remarks": data.approval_remarks,
                        "reviewed_by": current_user.get("name", "HOD")
                    }
                )

        # 3. When HOD/Admin edits another faculty's plan (without status change) -> Notify Faculty
        elif not data.status and current_user.get("role") in ["hod", "admin"]:
            course_recipients = await resolve_course_recipients(course_id_str, exclude_user_id=current_user["id"])
            for fac_uid in course_recipients:
                await dispatch_targeted_notification(
                    recipient_id=fac_uid,
                    actor_id=current_user["id"],
                    actor_name=current_user.get("name", "Manager"),
                    event_type="LESSON_PLAN_UPDATED",
                    entity_type="LESSON_PLAN",
                    entity_id=lesson_id,
                    course_id=course_id_str,
                    severity="INFO",
                    type="info",
                    title="Lesson Plan Updated",
                    message=f"Your lesson plan for {course_code} ({course_name}) was modified by {current_user.get('name')}.",
                    link=f"/lesson-plans/edit/{lesson_id}",
                    email_subject=f"Lesson Plan Updated: {course_code}",
                    metadata={
                        "course_code": course_code,
                        "course_name": course_name,
                        "updated_by": current_user.get("name")
                    }
                )

    return {"message": "Lesson plan updated successfully"}


@router.delete("/{lesson_id}")
async def remove_lesson_plan(
    lesson_id: str,
    current_user: dict = Depends(get_current_user),
):
    # Enforce ownership: faculty can delete their own lesson plans, managers any
    await _load_authorized_lesson(lesson_id, current_user)
    
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
