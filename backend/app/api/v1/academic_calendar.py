from fastapi import APIRouter, HTTPException

from app.schemas.academic_calendar_schema import AcademicCalendarCreate
from app.services.academic_calendar_service import create_calendar

router = APIRouter(
    prefix="/calendar",
    tags=["Academic Calendar"],
)


@router.post("/")
async def add_calendar(
    data: AcademicCalendarCreate,
):
    try:
        calendar_id = await create_calendar(data)

        return {
            "calendar_id": calendar_id,
            "message": "Academic Calendar created successfully",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )