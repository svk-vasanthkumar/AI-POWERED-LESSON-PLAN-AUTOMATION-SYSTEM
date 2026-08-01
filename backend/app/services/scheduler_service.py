from bson import ObjectId

from app.database.mongodb import get_database
from app.models.schedule_model import create_schedule_document


async def generate_schedule(course_id: str):
    db = get_database()

    course = await db.courses.find_one(
        {"_id": ObjectId(course_id)}
    )

    if not course:
        raise ValueError("Course not found")

    syllabus = await db.syllabi.find_one(
        {"course_id": course_id}
    )

    if not syllabus:
        raise ValueError("Syllabus not found")

    lesson = await db.lesson_plans.find_one(
        {
            "syllabus_id": syllabus["_id"]
        }
    )

    if not lesson:
        raise ValueError("Lesson Plan not found")

    timetable = await db.timetables.find_one(
        {
            "course_id": course_id
        }
    )

    if not timetable:
        raise ValueError("Timetable not found")

    schedule = []

    topics = lesson["lesson_plan"].split("\n")

    topic_index = 0

    for slot in timetable["schedule"]:

        if topic_index >= len(topics):
            break

        if topics[topic_index].strip():

            schedule.append(
                {
                    "day": slot["day"],
                    "start_time": slot["start_time"],
                    "end_time": slot["end_time"],
                    "topic": topics[topic_index],
                }
            )

            topic_index += 1

    document = create_schedule_document(
        course_id,
        str(lesson["_id"]),
        schedule,
    )

    result = await db.generated_schedules.insert_one(
        document
    )

    return {
        "schedule_id": str(result.inserted_id),
        "schedule": schedule,
    }