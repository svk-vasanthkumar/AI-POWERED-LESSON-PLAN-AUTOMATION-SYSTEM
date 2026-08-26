from pydantic import BaseModel, ConfigDict, Field


class LessonPlanUpdate(BaseModel):
    lesson_plan: str = Field(..., min_length=10)


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
    estimated_hours: float = Field(
        ...,
        ge=0,
        description="Teaching hours derived from the canonical syllabus",
    )
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
    """Top-level structured lesson plan.

    Since the canonical-syllabus rework this document is *assembled* rather than
    generated: units, unit titles, topics, hours and references come from the
    parsed syllabus, and only the pedagogical fields are contributed by the AI
    model. The shape is unchanged so the scheduler, exports and existing
    consumers keep working.
    """

    model_config = ConfigDict(extra="ignore")

    course_title: str
    course_objectives: list[str] = Field(default_factory=list)
    learning_outcomes: list[LearningOutcome] = Field(default_factory=list)
    units: list[UnitPlan] = Field(default_factory=list)
    overall_teaching_methods: list[str] = Field(default_factory=list)
    overall_assessment_methods: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AI enrichment schemas
#
# The AI model is NOT allowed to define the academic structure. It receives the
# canonical topics (parsed deterministically from the syllabus) and may only
# return pedagogical metadata keyed by ``topic_id``. Anything it returns for an
# unknown topic id is discarded during the merge, and topics it omits simply
# keep empty pedagogy — the structure can never change.
# ---------------------------------------------------------------------------


class TopicEnrichment(BaseModel):
    """Pedagogical metadata the model may attach to one canonical topic."""

    model_config = ConfigDict(extra="ignore")

    topic_id: str
    subtopics: list[str] = Field(default_factory=list)
    bloom_level: str | None = None
    learning_outcomes: list[str] = Field(default_factory=list)
    teaching_methods: list[str] = Field(default_factory=list)
    assessment_methods: list[str] = Field(default_factory=list)


class OutcomeEnrichment(BaseModel):
    """A Bloom level for a course outcome that the syllabus already defines."""

    model_config = ConfigDict(extra="ignore")

    outcome_id: str
    bloom_level: str | None = None


class LessonPlanEnrichment(BaseModel):
    """The complete, structure-free enrichment payload returned by the model."""

    model_config = ConfigDict(extra="ignore")

    topics: list[TopicEnrichment] = Field(default_factory=list)
    outcomes: list[OutcomeEnrichment] = Field(default_factory=list)
    overall_teaching_methods: list[str] = Field(default_factory=list)
    overall_assessment_methods: list[str] = Field(default_factory=list)