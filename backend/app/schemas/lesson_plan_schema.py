from pydantic import BaseModel, Field


class LessonPlanUpdate(BaseModel):
    lesson_plan: str = Field(..., min_length=10)