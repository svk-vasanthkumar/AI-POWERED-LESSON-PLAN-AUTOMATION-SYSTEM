from datetime import datetime, UTC


def create_schedule_document(
    course_id: str,
    lesson_plan_id: str,
    generated_schedule: list,
):
    return {
        "course_id": course_id,
        "lesson_plan_id": lesson_plan_id,
        "generated_schedule": generated_schedule,
        "created_at": datetime.now(UTC),
    }