"""Canonical-syllabus parser + coverage-validation tests.

The parser (:mod:`app.services.syllabus_parser`) is the single source of truth
for a course's academic structure — units, ordered topics, official hours,
outcomes and references — and it must be fully deterministic (no AI). These
tests pin down the guarantees the rest of the pipeline relies on:

  * every printed topic is preserved, in the exact order it appears,
  * stable ``U{unit}-T{order}`` topic ids,
  * official unit hours are read from the syllabus and flagged
    (``hours_source == "syllabus"``) and distributed across topics,
  * textbooks / references / outcomes / objectives are captured verbatim,
  * an unparseable document is REFUSED (``SyllabusParseError``) rather than
    silently yielding an empty or fabricated structure.

The second half exercises :func:`validate_topic_coverage`, the guard that
catches the "AI silently dropped Unit 4" class of bug: missing, duplicated,
unexpected or reordered topics are all reported.

Run: python -m pytest backend/tests/test_syllabus_parser.py -q
"""

import pytest

from app.services.lesson_plan_validation import validate_topic_coverage
from app.services.syllabus_parser import (
    SyllabusParseError,
    distribute_hours,
    parse_syllabus,
)


# ACE / Anna-University style syllabus. ``L T P C`` is on its own line so it is
# stripped as a credit-structure row (see ``normalize_text``).
ACE_SYLLABUS = """CS3491  ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING
L T P C
3 0 2 4

COURSE OBJECTIVES:
1. Study about uninformed and informed search techniques.
2. Learn probabilistic reasoning.

UNIT I  PROBLEM SOLVING   9
Introduction to AI, AI Applications, Problem solving agents, Search algorithms

UNIT II  PROBABILISTIC REASONING   9
Acting under uncertainty, Bayesian inference, Naive Bayes models

TOTAL: 45 PERIODS

COURSE OUTCOMES:
CO1: Explain autonomous agents.
CO2: Use appropriate search techniques.

TEXT BOOKS:
1. Russell and Norvig, Artificial Intelligence - A Modern Approach, 4th Edition

REFERENCES:
1. Dan Jurafsky, Speech and Language Processing
"""


# ---------------------------------------------------------------------------
# Structure, ordering, ids
# ---------------------------------------------------------------------------


def test_parses_course_code_and_title():
    c = parse_syllabus(ACE_SYLLABUS)
    assert c.course_code == "CS3491"
    assert "ARTIFICIAL INTELLIGENCE" in (c.course_title or "")


def test_units_and_ordered_topics_are_preserved():
    c = parse_syllabus(ACE_SYLLABUS)
    assert [u.unit_number for u in c.units] == [1, 2]
    # Topics appear in exactly the printed order, with stable ids.
    assert c.topic_ids == [
        "U1-T1", "U1-T2", "U1-T3", "U1-T4",
        "U2-T1", "U2-T2", "U2-T3",
    ]
    assert c.units[0].topics[0].topic == "Introduction to AI"
    assert c.units[0].topics[3].topic == "Search algorithms"
    assert c.units[1].topics[0].topic == "Acting under uncertainty"


def test_topic_count_matches_printed_topics():
    c = parse_syllabus(ACE_SYLLABUS)
    assert c.topic_count == 7


# ---------------------------------------------------------------------------
# Official hours (never invented)
# ---------------------------------------------------------------------------


def test_official_unit_hours_are_read_and_flagged():
    c = parse_syllabus(ACE_SYLLABUS)
    for unit in c.units:
        assert unit.hours == 9.0
        assert unit.hours_source == "syllabus"


def test_unit_hours_are_distributed_across_topics_without_loss():
    c = parse_syllabus(ACE_SYLLABUS)
    # 9h over 4 topics and 9h over 3 topics — the sum per unit is preserved.
    assert round(sum(t.hours for t in c.units[0].topics), 2) == 9.0
    assert round(sum(t.hours for t in c.units[1].topics), 2) == 9.0
    # Total required teaching hours == the sum of the two units' official hours.
    assert c.required_hours == 18.0


def test_total_hours_captured_from_document():
    c = parse_syllabus(ACE_SYLLABUS)
    assert c.total_hours == 45.0
    assert c.total_hours_source == "syllabus"


def test_distribute_hours_preserves_total_in_minutes():
    parts = distribute_hours(9, 7)
    assert len(parts) == 7
    # The split is exact in whole minutes (the unit the scheduler consumes);
    # converting back to hours only introduces sub-second rounding.
    assert sum(round(p * 60) for p in parts) == 9 * 60
    assert sum(parts) == pytest.approx(9.0, abs=1e-3)
    parts_zero = distribute_hours(0, 3)
    assert parts_zero == [0.0, 0.0, 0.0]
    assert distribute_hours(5, 0) == []


# ---------------------------------------------------------------------------
# Outcomes / textbooks / references / objectives
# ---------------------------------------------------------------------------


def test_outcomes_textbooks_references_objectives_captured():
    c = parse_syllabus(ACE_SYLLABUS)
    assert [o.outcome_id for o in c.course_outcomes] == ["CO1", "CO2"]
    assert any("autonomous agents" in o.description for o in c.course_outcomes)
    assert c.textbooks and "Russell and Norvig" in c.textbooks[0]
    assert c.references and "Dan Jurafsky" in c.references[0]
    assert len(c.course_objectives) == 2


# ---------------------------------------------------------------------------
# Unit numbering variants
# ---------------------------------------------------------------------------


def test_numeric_and_roman_unit_numbers_are_both_accepted():
    roman = parse_syllabus(ACE_SYLLABUS)
    numeric = parse_syllabus(
        ACE_SYLLABUS.replace("UNIT I ", "UNIT 1 ").replace("UNIT II ", "UNIT 2 ")
    )
    assert [u.unit_number for u in roman.units] == [1, 2]
    assert [u.unit_number for u in numeric.units] == [1, 2]


def test_duplicate_topic_names_are_both_preserved_with_distinct_ids():
    text = ACE_SYLLABUS.replace(
        "Introduction to AI, AI Applications, Problem solving agents, Search algorithms",
        "Introduction to AI, Search algorithms, Search algorithms",
    )
    c = parse_syllabus(text)
    # The parser never silently de-duplicates syllabus content.
    names = [t.topic for t in c.units[0].topics]
    assert names.count("Search algorithms") == 2
    assert [t.topic_id for t in c.units[0].topics] == ["U1-T1", "U1-T2", "U1-T3"]


# ---------------------------------------------------------------------------
# Refusal (never fabricate a structure)
# ---------------------------------------------------------------------------


def test_empty_document_is_refused():
    with pytest.raises(SyllabusParseError) as exc:
        parse_syllabus("   \n\n  ")
    assert exc.value.diagnostics["units_found"] == 0


def test_document_without_units_is_refused():
    with pytest.raises(SyllabusParseError):
        parse_syllabus("Just some prose with no unit headings at all.")


def test_unit_without_topics_is_refused():
    text = """UNIT I  EMPTY UNIT   9

UNIT II  HAS TOPICS   9
Topic one, Topic two
"""
    with pytest.raises(SyllabusParseError) as exc:
        parse_syllabus(text)
    # The diagnostics name the offending unit rather than guessing topics.
    assert 1 in exc.value.diagnostics["units_without_topics"]


# ---------------------------------------------------------------------------
# Coverage validation (structured plan vs canonical)
# ---------------------------------------------------------------------------


def _structured_from_ids(ids):
    return {"units": [{"unit_number": 1, "unit_title": "U",
                       "topics": [{"topic_id": tid, "topic": tid} for tid in ids]}]}


def test_coverage_complete_when_all_canonical_topics_present_in_order():
    c = parse_syllabus(ACE_SYLLABUS)
    report = validate_topic_coverage(c, _structured_from_ids(c.topic_ids))
    assert report["complete"] is True
    assert report["expected_count"] == report["actual_count"] == 7


def test_coverage_flags_missing_topic():
    c = parse_syllabus(ACE_SYLLABUS)
    dropped = [tid for tid in c.topic_ids if tid != "U2-T2"]
    report = validate_topic_coverage(c, _structured_from_ids(dropped))
    assert report["complete"] is False
    assert [m["topic_id"] for m in report["missing_topics"]] == ["U2-T2"]


def test_coverage_flags_duplicate_topic():
    c = parse_syllabus(ACE_SYLLABUS)
    dup = c.topic_ids + ["U1-T1"]
    report = validate_topic_coverage(c, _structured_from_ids(dup))
    assert report["complete"] is False
    assert "U1-T1" in report["duplicate_topics"]


def test_coverage_flags_unexpected_topic():
    c = parse_syllabus(ACE_SYLLABUS)
    extra = c.topic_ids + ["U9-T9"]
    report = validate_topic_coverage(c, _structured_from_ids(extra))
    assert report["complete"] is False
    assert "U9-T9" in report["unexpected_topics"]


def test_coverage_flags_reordered_topics():
    c = parse_syllabus(ACE_SYLLABUS)
    reordered = list(c.topic_ids)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    report = validate_topic_coverage(c, _structured_from_ids(reordered))
    assert report["complete"] is False
    assert report["order_preserved"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
