from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.models.modelCourse import create_course_document
from app.schemas.schemaCourse import CourseCreate, CourseResponse
from app.utils.utilityAuth import require_roles


router = APIRouter(
    prefix="/courses",
    tags=["Courses"],
)


@router.post(
    "/",
    response_model=CourseResponse,
)
async def create_course(
    data: CourseCreate,
    current_user=Depends(
        require_roles("admin", "hod")
    ),
):
    try:
        faculty_id = ObjectId(data.faculty_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid faculty ID",
        )

    faculty = await db.users.find_one(
        {
            "_id": faculty_id,
            "role": "faculty",
        }
    )

    if not faculty:
        raise HTTPException(
            status_code=404,
            detail="Faculty not found",
        )

    existing_course = await db.courses.find_one(
        {
            "course_code": data.course_code.upper()
        }
    )

    if existing_course:
        raise HTTPException(
            status_code=409,
            detail="Course code already exists",
        )

    course = create_course_document(
        course_code=data.course_code,
        course_name=data.course_name,
        department=data.department,
        semester=data.semester,
        credits=data.credits,
        faculty_id=data.faculty_id,
    )

    await db.courses.insert_one(course)

    return CourseResponse(
        course_id=str(course["_id"]),
        course_code=course["course_code"],
        course_name=course["course_name"],
        department=course["department"],
        semester=course["semester"],
        credits=course["credits"],
        faculty_id=str(course["faculty_id"]),
    )