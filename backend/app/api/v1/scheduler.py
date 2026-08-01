from fastapi import APIRouter, HTTPException

from app.services.scheduler_service import generate_schedule

router = APIRouter(
    prefix="/scheduler",
    tags=["Scheduler"],
)


@router.post("/{course_id}")
async def generate(course_id: str):
    try:
        return await generate_schedule(course_id)

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )