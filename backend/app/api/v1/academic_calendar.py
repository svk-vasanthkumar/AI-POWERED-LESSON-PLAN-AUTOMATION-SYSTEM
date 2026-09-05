import os
import tempfile

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)

from app.auth.dependencies import (
    get_current_user,
    require_roles,
)
from app.config.logger import logger
from app.schemas.academic_calendar_schema import (
    AcademicCalendarCreate,
    AcademicCalendarUpdate,
)
from app.services.academic_calendar_service import (
    CalendarAlreadyExistsError,
    confirm_calendar,
    create_calendar,
    create_pending_calendar,
    delete_calendar,
    get_all_calendars,
    get_calendar,
    get_pending_calendar,
    process_calendar_document,
    update_calendar,
)
from app.services.text_extraction_service import (
    DocumentExtractionError,
    DocumentOCRProcessingError,
    DocumentOCRUnavailableError,
)

router = APIRouter(
    prefix="/calendar",
    tags=["Academic Calendar"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/",
)
async def create_new_calendar(
    data: AcademicCalendarCreate,
    current_user=Depends(require_roles("admin", "hod")),
):
    try:
        calendar_id = await create_calendar(data)
        return {
            "calendar_id": calendar_id,
            "message": "Academic calendar created successfully.",
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/upload",
)
async def upload_calendar(
    file: UploadFile = File(...),
    current_user=Depends(require_roles("admin", "hod")),
):
    """Upload the official college academic calendar.

    The document is extracted and parsed into a pending review record.
    """
    filename = file.filename or ""
    extension = os.path.splitext(filename)[1].lower()

    allowed_extensions = {
        ".pdf",
        ".docx",
        ".jpg",
        ".jpeg",
        ".png",
    }

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, DOCX, and image academic calendar files are supported.",
        )

    temporary_path = None

    try:
        content = await file.read()

        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=extension,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_path = temporary_file.name

        try:
            result = await process_calendar_document(
                filepath=temporary_path,
                filename=filename,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
        except DocumentOCRUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            )
        except DocumentOCRProcessingError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
        except DocumentExtractionError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
        except Exception:
            logger.exception("Unexpected academic calendar upload failure")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to process the academic calendar document.",
            )

        calendar = result["calendar"]

        try:
            calendar_id = await create_pending_calendar(calendar)
        except CalendarAlreadyExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )

        return {
            "calendar_id": calendar_id,
            "filename": filename,
            "extraction_method": result["extraction_method"],
            "extraction_status": "needs_review",
            "calendar": calendar.model_dump(mode="json"),
            "raw_text": result["raw_text"],
            "message": (
                "Academic calendar extracted successfully. "
                "Review it before confirmation."
            ),
        }

    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


@router.get("/")
async def list_calendars():
    return await get_all_calendars()


@router.get("/{calendar_id}/preview")
async def preview_calendar(
    calendar_id: str,
):
    calendar = await get_pending_calendar(calendar_id)

    if not calendar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending academic calendar not found.",
        )

    return {
        "calendar_id": calendar_id,
        "status": "pending_review",
        "calendar": calendar,
    }


@router.get("/{calendar_id}")
async def single_calendar(
    calendar_id: str,
):
    calendar = await get_calendar(calendar_id)

    if not calendar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academic calendar not found.",
        )

    return calendar


@router.post(
    "/{calendar_id}/confirm",
)
async def confirm_uploaded_calendar(
    calendar_id: str,
    current_user=Depends(require_roles("admin", "hod")),
):
    confirmed = await confirm_calendar(calendar_id)

    if not confirmed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending academic calendar not found.",
        )

    return {
        "calendar_id": calendar_id,
        "status": "confirmed",
        "message": "Academic calendar confirmed successfully.",
    }


@router.put(
    "/{calendar_id}",
)
async def edit_calendar(
    calendar_id: str,
    data: AcademicCalendarUpdate,
    current_user=Depends(require_roles("admin", "hod")),
):
    updated = await update_calendar(
        calendar_id,
        data,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academic calendar not found or no changes were applied.",
        )

    return {
        "calendar_id": calendar_id,
        "message": "Academic calendar updated successfully.",
    }


@router.delete(
    "/{calendar_id}",
)
async def remove_calendar(
    calendar_id: str,
    current_user=Depends(require_roles("admin", "hod")),
):
    deleted = await delete_calendar(calendar_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academic calendar not found.",
        )

    return {
        "message": "Academic calendar deleted successfully."
    }