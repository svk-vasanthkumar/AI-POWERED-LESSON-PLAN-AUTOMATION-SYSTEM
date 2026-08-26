"""Coverage validation for lesson plans and generated schedules.

Two independent questions are answered here, and both are answered against the
canonical syllabus — never against the AI output:

1. **Topic coverage** (:func:`validate_topic_coverage`) — does the structured
   lesson plan contain exactly the canonical topics, in canonical order? This is
   what catches the "AI silently dropped Unit 4" class of bug. Any deviation is
   reported rather than tolerated.

2. **Schedule coverage** (:func:`validate_schedule_coverage`) — did the
   scheduler actually place every canonical topic (and all of its required
   hours) inside the semester window? Topics that did not fit are reported with
   ``complete: false`` so the UI and the exports can show the gap instead of
   pretending the plan is finished.

Neither function raises: they return structured reports. Callers decide whether
a given deviation is fatal (lesson-plan generation) or merely informational (a
semester window that ran out of teaching days).
"""

from __future__ import annotations

from app.schemas.syllabus_schema import CanonicalSyllabus

# Fractional-hour tolerance, matching the scheduler engine's own epsilon so
# rounding never manufactures a phantom "0.01 hours unscheduled" warning.
_EPSILON = 0.011


def _structured_topic_ids(structured_plan: dict | None) -> list[str]:
    """Every ``topic_id`` in a structured plan, in document order."""
    ids: list[str] = []
    if not isinstance(structured_plan, dict):
        return ids
    for unit in structured_plan.get("units") or []:
        if not isinstance(unit, dict):
            continue
        for topic in unit.get("topics") or []:
            if isinstance(topic, dict) and topic.get("topic_id") is not None:
                ids.append(str(topic["topic_id"]))
    return ids


def validate_topic_coverage(
    canonical: CanonicalSyllabus,
    structured_plan: dict | None,
) -> dict:
    """Compare a structured lesson plan against the canonical syllabus.

    Returns a report with:
        ``complete``          -- no missing, unexpected, duplicate or reordered topics
        ``expected_count``    -- canonical topic count
        ``actual_count``      -- topics present in the structured plan
        ``missing_topics``    -- canonical topics absent from the plan
        ``unexpected_topics`` -- plan topic ids with no canonical counterpart
        ``duplicate_topics``  -- topic ids appearing more than once in the plan
        ``order_preserved``   -- canonical ordering respected
    """
    expected = canonical.topic_ids
    expected_set = set(expected)
    actual = _structured_topic_ids(structured_plan)

    seen: set[str] = set()
    duplicates: list[str] = []
    for topic_id in actual:
        if topic_id in seen and topic_id not in duplicates:
            duplicates.append(topic_id)
        seen.add(topic_id)

    actual_set = set(actual)
    missing = [tid for tid in expected if tid not in actual_set]
    unexpected = [tid for tid in actual if tid not in expected_set]

    # Order check: the canonical ids, in the order they appear in the plan.
    filtered = [tid for tid in actual if tid in expected_set]
    deduped: list[str] = []
    for topic_id in filtered:
        if topic_id not in deduped:
            deduped.append(topic_id)
    order_preserved = deduped == [tid for tid in expected if tid in actual_set]

    missing_detail = []
    if missing:
        by_id = {topic.topic_id: (unit, topic) for unit, topic in canonical.iter_topics()}
        for topic_id in missing:
            unit, topic = by_id[topic_id]
            missing_detail.append(
                {
                    "topic_id": topic_id,
                    "topic": topic.topic,
                    "unit_number": unit.unit_number,
                }
            )

    return {
        "complete": not missing and not unexpected and not duplicates and order_preserved,
        "expected_count": len(expected),
        "actual_count": len(actual),
        "missing_topics": missing_detail,
        "unexpected_topics": unexpected,
        "duplicate_topics": duplicates,
        "order_preserved": order_preserved,
    }


def validate_schedule_coverage(
    canonical: CanonicalSyllabus,
    sessions: list[dict] | None,
) -> dict:
    """Check that every canonical topic-hour was placed on the calendar.

    ``sessions`` are the generated schedule's sessions (each carrying
    ``topic_id`` and ``duration_hours``). Returns a report with the required vs
    scheduled hours, the topics that were fully or partially left out, and a
    ``complete`` flag. Extra scheduled hours are reported but never subtracted
    from another topic.
    """
    scheduled_hours: dict[str, float] = {}
    for session in sessions or []:
        if not isinstance(session, dict):
            continue
        topic_id = session.get("topic_id")
        if topic_id is None:
            continue
        try:
            hours = float(session.get("duration_hours") or 0)
        except (TypeError, ValueError):
            hours = 0.0
        scheduled_hours[str(topic_id)] = scheduled_hours.get(str(topic_id), 0.0) + hours

    required_total = 0.0
    scheduled_total = 0.0
    unscheduled: list[dict] = []
    partially: list[dict] = []

    for unit, topic in canonical.iter_topics():
        required = float(topic.hours or 0)
        placed = scheduled_hours.get(topic.topic_id, 0.0)
        
        required_total += required
        
        if required > 0:
            scheduled_total += min(placed, required)

        if placed <= _EPSILON and required > _EPSILON:
            unscheduled.append(
                {
                    "topic_id": topic.topic_id,
                    "topic": topic.topic,
                    "unit_number": unit.unit_number,
                    "required_hours": round(required, 2),
                    "scheduled_hours": 0.0,
                }
            )
        elif required - placed > _EPSILON:
            partially.append(
                {
                    "topic_id": topic.topic_id,
                    "topic": topic.topic,
                    "unit_number": unit.unit_number,
                    "required_hours": round(required, 2),
                    "scheduled_hours": round(placed, 2),
                }
            )

    known_ids = set(canonical.topic_ids)
    orphan_sessions = sorted(tid for tid in scheduled_hours if tid not in known_ids)

    return {
        "complete": not unscheduled and not partially,
        "required_hours": round(required_total, 2),
        "scheduled_hours": round(scheduled_total, 2),
        "unscheduled_hours": round(max(required_total - scheduled_total, 0.0), 2),
        "total_topics": canonical.topic_count,
        "scheduled_topics": len(
            [tid for tid in known_ids if scheduled_hours.get(tid, 0.0) > _EPSILON]
        ),
        "unscheduled_topics": unscheduled,
        "partially_scheduled_topics": partially,
        "orphan_session_topic_ids": orphan_sessions,
    }