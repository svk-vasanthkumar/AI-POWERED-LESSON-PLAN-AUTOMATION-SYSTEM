"""Canonical syllabus schemas.

These model the *authoritative* academic structure extracted deterministically
from an uploaded syllabus document (see ``app.services.syllabus_parser``).

Why this exists
---------------
Previously the AI model was the only thing that produced units / topics / hours
/ references, which meant the model effectively *invented* the syllabus: topics
went missing, teaching hours were guessed and textbook references were
fabricated. The canonical syllabus fixes the ownership of that data:

  * The syllabus document owns units, unit titles, ordered topics, official unit
    hours, course outcomes and textbooks/references.
  * The AI model may only *enrich* those topics (pedagogy, Bloom level,
    outcomes, assessment). It can never add, remove or reorder them.

Every hours value records where it came from via ``hours_source`` so the API and
the exports can always tell an official syllabus figure apart from a derived
one. Nothing here is ever guessed silently.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Where an hours figure came from.
#   "syllabus" -> printed in the syllabus document (authoritative)
#   "derived"  -> computed from another authoritative figure (e.g. a unit's
#                 official hours split across its topics, or a printed total
#                 divided across units)
#   "default"  -> no hours information existed anywhere in the document; a
#                 neutral fallback was used and MUST be surfaced as such
HoursSource = Literal["syllabus", "derived", "default"]


class CanonicalTopic(BaseModel):
    """One teachable topic exactly as printed in the syllabus."""

    model_config = ConfigDict(extra="forbid")

    topic_id: str = Field(..., description="Stable id, e.g. 'U1-T3'")
    topic: str = Field(..., min_length=1)
    unit_number: int = Field(..., ge=1)
    order: int = Field(..., ge=1, description="1-based position within the unit")
    hours: float = Field(..., ge=0)
    hours_source: HoursSource = "derived"


class CanonicalUnit(BaseModel):
    """One syllabus unit with its official hours and ordered topics."""

    model_config = ConfigDict(extra="forbid")

    unit_number: int = Field(..., ge=1)
    unit_title: str = ""
    hours: float | None = Field(default=None, ge=0)
    hours_source: HoursSource = "default"
    topics: list[CanonicalTopic] = Field(default_factory=list)


class CanonicalOutcome(BaseModel):
    """A course outcome (CO) as printed in the syllabus."""

    model_config = ConfigDict(extra="forbid")

    outcome_id: str
    description: str = ""


class CanonicalSyllabus(BaseModel):
    """The full authoritative structure parsed from a syllabus document."""

    model_config = ConfigDict(extra="forbid")

    course_code: str | None = None
    course_title: str | None = None
    units: list[CanonicalUnit] = Field(default_factory=list)
    course_objectives: list[str] = Field(default_factory=list)
    course_outcomes: list[CanonicalOutcome] = Field(default_factory=list)
    textbooks: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    total_hours: float | None = Field(default=None, ge=0)
    total_hours_source: HoursSource = "default"

    def iter_topics(self):
        """Yield every topic in canonical (unit, then topic) order."""
        for unit in self.units:
            for topic in unit.topics:
                yield unit, topic

    @property
    def topic_ids(self) -> list[str]:
        return [topic.topic_id for _, topic in self.iter_topics()]

    @property
    def topic_count(self) -> int:
        return sum(len(unit.topics) for unit in self.units)

    @property
    def required_hours(self) -> float:
        """Total teaching hours the syllabus requires across all topics."""
        return round(sum(topic.hours for _, topic in self.iter_topics()), 2)
