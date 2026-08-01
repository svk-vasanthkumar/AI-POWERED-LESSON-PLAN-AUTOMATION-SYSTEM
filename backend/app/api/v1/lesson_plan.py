from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, status

from app.database.mongodb import get_database
from app.schemas.lesson_plan_schema import LessonPlanUpdate
from app.services.lesson_plan_service import generate_and_save_lesson_plan

router = APIRouter(
    prefix="/lesson-plan",
    tags=["Lesson Plan"],
)


@router.post("/generate/{syllabus_id}")
async def generate(syllabus_id: str):
    try:
        return await generate_and_save_lesson_plan(syllabus_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/")
async def get_all_lesson_plans():
    db = get_database()
    lesson_plans = []

    async for lesson in db.lesson_plans.find():
        lesson["_id"] = str(lesson["_id"])

        if "syllabus_id" in lesson:
            lesson["syllabus_id"] = str(lesson["syllabus_id"])

        if "course_id" in lesson:
            lesson["course_id"] = str(lesson["course_id"])

        lesson_plans.append(lesson)

    return lesson_plans


@router.get("/{lesson_id}")
async def get_lesson_plan(lesson_id: str):
    db = get_database()

    try:
        obj_id = ObjectId(lesson_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson plan not found",
        )

    lesson = await db.lesson_plans.find_one({"_id": obj_id})

    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson plan not found",
        )

    lesson["_id"] = str(lesson["_id"])

    if "syllabus_id" in lesson:
        lesson["syllabus_id"] = str(lesson["syllabus_id"])

    if "course_id" in lesson:
        lesson["course_id"] = str(lesson["course_id"])

    return lesson


@router.put("/{lesson_id}")
async def update_lesson_plan(lesson_id: str, data: LessonPlanUpdate):
    db = get_database()

    try:
        obj_id = ObjectId(lesson_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson plan not found",
        )

    result = await db.lesson_plans.update_one(
        {"_id": obj_id},
        {"$set": {"lesson_plan": data.lesson_plan}},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson plan not found",
        )

    return {"message": "Lesson plan updated successfully"}


@router.delete("/{lesson_id}")
async def delete_lesson_plan(lesson_id: str):
    db = get_database()

    try:
        obj_id = ObjectId(lesson_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson plan not found",
        )

    result = await db.lesson_plans.delete_one({"_id": obj_id})

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson plan not found",
        )

    return {"message": "Lesson plan deleted successfully"}