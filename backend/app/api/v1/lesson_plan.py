from fastapi import APIRouter, HTTPException
from app.database.mongodb import get_database
from bson import ObjectId
from app.schemas.lesson_plan_schema import LessonPlanUpdate
from app.services.lesson_plan_service import generate_and_save_lesson_plan

router = APIRouter(
    prefix="/lesson-plan",
    tags=["Lesson Plan"]
)


@router.post("/generate/{syllabus_id}")
async def generate(syllabus_id: str):
    try:
        return await generate_and_save_lesson_plan(
            syllabus_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
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


@router.delete("/{lesson_id}")
async def delete_lesson_plan(lesson_id: str):
    db = get_database()

    result = await db.lesson_plans.delete_one(
        {"_id": ObjectId(lesson_id)}
    )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Lesson plan not found"
        )

    return {
        "message": "Lesson plan deleted successfully"
    }