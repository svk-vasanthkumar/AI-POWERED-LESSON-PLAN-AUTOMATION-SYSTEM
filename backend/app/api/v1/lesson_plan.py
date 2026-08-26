from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.dependencies import get_current_user, require_roles
from app.auth.resource_access import (
    accessible_course_ids,
    ensure_course_id_access,
    ids_match,
    is_manager,
)
from app.database.mongodb import get_database
from app.models.schedule_model import serialize_schedule
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
    LessonPlanCoverageError,
    LessonPlanInUseError,
    delete_lesson_plan,
    generate_and_save_lesson_plan,
)
from app.services.syllabus_parser import SyllabusParseError

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


def _oid_variants(value) -> list:
    """Both ObjectId and string forms of an id, for legacy-compatible ``$in``."""
    if value is None:
        return []
    variants = [value, str(value)]
    if not isinstance(value, ObjectId):
        try:
            variants.append(ObjectId(str(value)))
        except Exception:
            pass
    seen: set = set()
    unique: list = []
    for item in variants:
        key = (type(item).__name__, str(item))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


async def _active_schedule_for_lesson(db, lesson: dict) -> dict | None:
    """Locate the active generated schedule that belongs to a lesson plan.

    Lookup order (Task #7), never attaching another faculty/course's schedule:

      1. ``generated_schedules.lesson_plan_id == lesson._id`` AND ``active``
         (the direct, unambiguous link).
      2. Fallback: ``course_id == lesson.course_id`` AND ``active`` (older
         schedules generated before ``lesson_plan_id`` was stored).

    The newest version is preferred in both cases.
    """
    schedule = await db.generated_schedules.find_one(
        {"lesson_plan_id": {"$in": _oid_variants(lesson.get("_id"))}, "active": True},
        sort=[("version", -1)],
    )
    if schedule is None and lesson.get("course_id") is not None:
        schedule = await db.generated_schedules.find_one(
            {"course_id": {"$in": _oid_variants(lesson.get("course_id"))}, "active": True},
            sort=[("version", -1)],
        )
    return schedule


def _present_session(session: dict) -> dict:
    """Expose a scheduler session with frontend-friendly ``planned_*`` fields.

    The deterministic scheduler stores each session's ``date``/``day`` and its
    period grid (``period_start``/``period_end``) or legacy clock times. These
    are surfaced verbatim under explicit ``planned_*`` keys so the frontend
    never has to fabricate a date or period. Original fields are retained for
    backward compatibility. Values are taken as-is from the scheduler; nothing
    is invented here.
    """
    out = dict(session)
    out["planned_date"] = session.get("date")
    out["planned_day"] = session.get("day")
    out["planned_period_start"] = session.get("period_start")
    out["planned_period_end"] = session.get("period_end")
    out["planned_start_time"] = session.get("start_time")
    out["planned_end_time"] = session.get("end_time")
    return out


def _present_schedule(schedule: dict | None) -> dict | None:
    """Shape an active schedule for the lesson-plan response (Task #7-9).

    Returns ``None`` when no schedule exists yet (a lesson plan can be read
    before it is scheduled — its canonical topics still live in
    ``structured_plan``). Otherwise returns the schedule identity plus its
    sessions carrying explicit ``planned_*`` date/period fields.
    """
    if not schedule:
        return None
    serialized = serialize_schedule(schedule)
    sessions = [
        _present_session(s)
        for s in (serialized.get("sessions") or [])
        if isinstance(s, dict)
    ]
    return {
        "schedule_id": serialized.get("_id"),
        "version": serialized.get("version"),
        "active": serialized.get("active"),
        "status": serialized.get("status"),
        "total_hours": serialized.get("total_hours"),
        "scheduling_mode": serialized.get("scheduling_mode"),
        "academic_year": serialized.get("academic_year"),
        "semester": serialized.get("semester"),
        "sessions": sessions,
    }


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
async def generate(
    syllabus_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate a lesson plan for a syllabus (authenticated, ownership-scoped).

    The router already rejects unauthenticated callers (401). Here a faculty is
    additionally restricted to syllabi belonging to a course they own (403);
    admin/hod may generate for any course.
    """
    db = get_database()

    # Ownership is enforced against the syllabus's parent course BEFORE any
    # (potentially expensive) parsing / AI work happens. A malformed id -> 400,
    # an unknown syllabus -> 404, an unowned syllabus -> 403.
    syllabus_oid = to_object_id(syllabus_id, field="syllabus_id")
    syllabus = await db.syllabi.find_one({"_id": syllabus_oid})
    if syllabus is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Syllabus not found",
        )
    course_id = to_object_id(syllabus["course_id"], field="course_id")
    await ensure_course_id_access(db, current_user, course_id)

    try:
        return await generate_and_save_lesson_plan(syllabus_id)
    except SyllabusParseError as e:
        # The syllabus structure could not be recovered. Refuse rather than
        # letting an AI-invented structure through. The safe diagnostics explain
        # what was (and was not) found without leaking internals.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(e), "diagnostics": getattr(e, "diagnostics", {})},
        )
    except LessonPlanCoverageError as e:
        # The assembled plan did not cover every canonical topic — never save an
        # incomplete plan.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(e), "coverage": e.coverage},
        )
    except AIServiceUnavailableError as e:
        # Defensive: the generation pipeline degrades gracefully on AI failure,
        # so this is not normally reachable. Kept so a future non-degrading path
        # still surfaces a safe, retryable 503 (never provider internals).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except AIGenerationError as e:
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
    """Return a lesson plan together with its active schedule (Task #7-10).

    The response always contains the full ``structured_plan`` (every canonical
    topic, even ones not yet scheduled) plus a ``schedule`` object exposing the
    deterministic planned date/day and planned period(s) for each scheduled
    session. ``schedule`` is ``null`` when the plan has not been scheduled yet,
    so unscheduled topics simply have no planned date/period rather than
    disappearing.
    """
    lesson = await _load_authorized_lesson(lesson_id, current_user)
    db = get_database()
    schedule = await _active_schedule_for_lesson(db, lesson)

    payload = _serialize_lesson(lesson)
    payload["schedule"] = _present_schedule(schedule)
    return payload


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
