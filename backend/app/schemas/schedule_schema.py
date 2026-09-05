from pydantic import BaseModel, Field
from typing import Optional, List

class ExamConfigInput(BaseModel):
    exam_type: str = Field(default="CIA", description="Type of exam (e.g. CIA, Unit Test)")
    start_date: str = Field(..., description="Start date of the exam window (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date of the exam window (YYYY-MM-DD)")
    exam_days: List[str] = Field(..., description="List of days (e.g., ['Monday', 'Saturday']) the exam takes place on")
    duration: int = Field(default=2, description="Duration in hours for the exam (e.g., first 2 hours)")

class GenerateScheduleRequest(BaseModel):
    exam_configs: Optional[List[ExamConfigInput]] = Field(
        default=None, 
        description="Optional list of CIA exam configurations to override standard class hours."
    )
