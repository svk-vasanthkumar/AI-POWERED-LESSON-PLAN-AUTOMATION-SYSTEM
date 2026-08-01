from fastapi import APIRouter, HTTPException

from app.schemas.timetable_schema import TimetableCreate
from app.services.timetable_service import create_timetable

router = APIRouter(
    prefix="/timetable",
    tags=["Timetable"],
)


@router.post("/")
async def add_timetable(data: TimetableCreate):
    try:
        timetable_id = await create_timetable(data)

        return {
            "timetable_id": timetable_id,
            "message": "Timetable created successfully",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )