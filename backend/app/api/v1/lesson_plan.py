from fastapi import APIRouter, HTTPException
from app.database.mongodb import get_database
from bson import ObjectId
from app.schemas.lesson_plan_schema import LessonPlanUpdate

router = APIRouter(
    prefix="/lesson-plan",
    tags=["Lesson Plan"]
)


@router.get("/")
async def get_all_lesson_plans():
    db = get_database()

    lesson_plans = []

    async for lesson in db.lesson_plans.find():
        lesson["_id"] = str(lesson["_id"])
        lesson_plans.append(lesson)

    return lesson_plans


@router.get("/{lesson_id}")
async def get_lesson_plan(lesson_id: str):
    db = get_database()

    lesson = await db.lesson_plans.find_one(
        {"_id": ObjectId(lesson_id)}
    )

    if not lesson:
        raise HTTPException(
            status_code=404,
            detail="Lesson plan not found"
        )

    lesson["_id"] = str(lesson["_id"])

    return lesson


@router.put("/{lesson_id}")
async def update_lesson_plan(
    lesson_id: str,
    data: LessonPlanUpdate
):
    db = get_database()

    result = await db.lesson_plans.update_one(
        {"_id": ObjectId(lesson_id)},
        {
            "$set": {
                "lesson_plan": data.lesson_plan
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Lesson plan not found"
        )

    return {
        "message": "Lesson plan updated successfully"
    }