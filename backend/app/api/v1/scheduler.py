from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.dependencies import get_current_user
from app.schemas.progress_schema import SessionRescheduleRequest, SessionStatusUpdate
from app.services.export_service import (
    DocumentGenerationError,
    EmptyScheduleError,
    build_schedule_export,
)
from app.services.progress_service import (
    ProgressPermissionError,
    SessionNotFoundError,
    get_course_progress,
    reschedule_session,
    update_session_status,
)
from app.services.scheduler_engine import (
    ScheduleConflictError,
    SchedulerValidationError,
)
from app.services.scheduler_service import (
    ScheduleNotFoundError,
    generate_schedule,
    get_latest_schedule,
)

# Every scheduler endpoint requires a valid Bearer JWT.
# All roles (admin, hod, faculty) may generate / read a schedule.
router = APIRouter(
    prefix="/scheduler",
    tags=["Scheduler"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/{course_id}")
async def generate(
    course_id: str,
    academic_year: str | None = Query(
        default=None,
        description=(
            "Academic year (e.g. '2024-2025') used to select the academic "
            "calendar when a course maps to more than one. Optional; resolved "
            "from the course/timetable when omitted."
        ),
    ),
    calendar_id: str | None = Query(
        default=None,
        description="Optional explicit calendar ID to use for scheduling.",
    ),
    timetable_id: str | None = Query(
        default=None,
        description="Optional explicit timetable ID to use for scheduling.",
    ),
):
    """Generate (or regenerate) a conflict-free schedule for a course.

    Controlled error mapping (Phase 15):
        400  invalid ObjectId (raised by ``to_object_id``)
        422  missing structured plan / invalid calendar / invalid timetable /
             ambiguous academic year / timetable-faculty mismatch
        404  course / lesson plan / calendar / timetable not found
        409  schedule conflict (with a structured conflict report)
        500  handled by the global exception handler (never leaks internals)
    """
    try:
        return await generate_schedule(
            course_id, 
            academic_year=academic_year,
            calendar_id=calendar_id,
            timetable_id=timetable_id
        )

    except SchedulerValidationError as e:
        # Missing structured plan / invalid calendar dates / invalid timetable.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ScheduleConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Schedule conflict detected",
                "conflicts": e.conflicts,
            },
        )


@router.get("/{course_id}")
async def get_schedule(course_id: str):
    """Return the latest generated schedule for a course (Phase 12)."""
    try:
        return await get_latest_schedule(course_id)

    except ScheduleNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# Progress monitoring & schedule-deviation tracking
#
# Both endpoints reuse the router-level JWT dependency so every call requires a
# valid Bearer token. Progress is DERIVED from the sessions stored in the active
# generated schedule — no separate progress collection is created (Phase 14).
#
# Controlled error mapping (Phases 15 & 17):
#     400  malformed course_id            (raised by ``to_object_id``)
#     404  course / active schedule / session not found
#     422  invalid status / invalid actual_date
#     403  authenticated but not permitted to edit this schedule
#     500  handled by the global exception handler (never leaks internals)
# ---------------------------------------------------------------------------


@router.patch("/{course_id}/sessions/{session_id}")
async def patch_session_status(
    course_id: str,
    session_id: str,
    payload: SessionStatusUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update a single schedule session's teaching status (Phases 3-5).

    ``session_id`` is either the session's stable ``session_id`` or its
    zero-based array index (legacy addressing), both surfaced by the progress
    endpoint. Only that session is modified; planned fields are preserved and
    execution data (executed date/periods, actual hours, actual topics,
    remarks) is stored separately. Invalid status transitions and invalid
    execution data return 422.
    """
    try:
        return await update_session_status(
            course_id=course_id,
            session_id=session_id,
            status_value=payload.status.value,
            actual_date=payload.actual_date,
            current_user=current_user,
            executed_date=payload.executed_date,
            executed_period_start=payload.executed_period_start,
            executed_period_end=payload.executed_period_end,
            actual_hours=payload.actual_hours,
            actual_topics=payload.actual_topics,
            remarks=payload.remarks,
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ScheduleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ProgressPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except SchedulerValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )


@router.post("/{course_id}/sessions/{session_id}/reschedule")
async def reschedule_session_endpoint(
    course_id: str,
    session_id: str,
    payload: SessionRescheduleRequest,
    current_user: dict = Depends(get_current_user),
):
    """Safely reschedule a session to another valid slot (Task #6 req. 7).

    The new date is validated against the academic calendar (holidays / exams /
    vacation / non-working days are rejected with 422) and, when a period is
    supplied, against the faculty timetable (422). Faculty conflicts return 409.
    The original planned date/period are preserved; the new slot is stored in
    ``rescheduled_*`` fields and the session's status becomes ``rescheduled``.
    """
    try:
        return await reschedule_session(
            course_id=course_id,
            session_id=session_id,
            new_date=payload.new_date,
            current_user=current_user,
            new_period_start=payload.new_period_start,
            new_period_end=payload.new_period_end,
            actual_topics=payload.actual_topics,
            remarks=payload.remarks,
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ScheduleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ProgressPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ScheduleConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Schedule conflict detected",
                "conflicts": e.conflicts,
            },
        )
    except SchedulerValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )


@router.get("/{course_id}/progress")
async def get_progress(course_id: str):
    """Return derived course/syllabus progress + deviations (Phase 12)."""
    try:
        return await get_course_progress(course_id)

    except ScheduleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# Deterministic schedule exports (PDF / DOCX / XLSX)
#
# Reuse the router-level JWT dependency so every export requires a valid Bearer
# token (no public export endpoints). Exports READ the latest active generated
# schedule only — they never trigger schedule generation.
#
# Controlled error mapping (Phase 11):
#     400  malformed ObjectId          (raised by ``to_object_id``)
#     404  no schedule for the course   (ScheduleNotFoundError)
#     422  schedule has no sessions      (EmptyScheduleError)
#     500  document generation failure   (DocumentGenerationError; internals are
#          logged server-side and never surfaced to the client)
# ---------------------------------------------------------------------------


async def _export_schedule_response(course_id: str, fmt: str) -> Response:
    try:
        content, filename, media_type = await build_schedule_export(course_id, fmt)
    except ScheduleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except EmptyScheduleError as e:
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


@router.get("/{course_id}/export/pdf")
async def export_schedule_as_pdf(course_id: str):
    return await _export_schedule_response(course_id, "pdf")


@router.get("/{course_id}/export/docx")
async def export_schedule_as_docx(course_id: str):
    return await _export_schedule_response(course_id, "docx")


@router.get("/{course_id}/export/xlsx")
async def export_schedule_as_xlsx(course_id: str):
    return await _export_schedule_response(course_id, "xlsx")
