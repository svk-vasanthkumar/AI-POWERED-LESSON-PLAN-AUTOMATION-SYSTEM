from pydantic import BaseModel, ConfigDict, Field


class LessonPlanUpdate(BaseModel):
    lesson_plan: str | None = Field(default=None, min_length=10)
    sessions: list[dict] | None = None
    status: str | None = None


# ---------------------------------------------------------------------------
# Structured AI lesson-plan output schemas
#
# These model the JSON the Groq model is instructed to return. They are used to
# validate the AI response before it is persisted so the scheduler / frontend
# can consume clean, typed data instead of a free-form Markdown blob.
#
# The schemas are intentionally lenient about *optional collections* (they
# default to empty lists) so minor omissions from the model do not fail the
# whole generation, while still enforcing the structural essentials (numeric
# hours, integer unit numbers, required titles, nested topics).
# ---------------------------------------------------------------------------


class LearningOutcome(BaseModel):
    model_config = ConfigDict(extra="ignore")

    outcome_id: str = Field(..., description="Stable id, e.g. 'CO1'")
    description: str
    bloom_level: str = Field(..., description="Bloom's taxonomy level, e.g. 'Understand'")


class TopicPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic_id: str = Field(..., description="Stable id, e.g. 'U1-T1'")
    topic: str
    subtopics: list[str] = Field(default_factory=list)
    estimated_hours: float = Field(default=1, ge=0, description="Realistic teaching hours")
    bloom_level: str | None = None
    learning_outcomes: list[str] = Field(
        default_factory=list, description="Referenced learning-outcome ids, e.g. ['CO1']"
    )
    teaching_methods: list[str] = Field(default_factory=list)
    assessment_methods: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class UnitPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    unit_number: int = Field(..., ge=1)
    unit_title: str
    topics: list[TopicPlan] = Field(default_factory=list)


class LessonPlanAIOutput(BaseModel):
    """Top-level structured lesson plan returned by the AI generation service."""

    model_config = ConfigDict(extra="ignore")

    course_title: str
    course_objectives: list[str] = Field(default_factory=list)
    learning_outcomes: list[LearningOutcome] = Field(default_factory=list)
    units: list[UnitPlan] = Field(default_factory=list)
    overall_teaching_methods: list[str] = Field(default_factory=list)
    overall_assessment_methods: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
