"""Deterministic syllabus parser (no AI involved).

This module is the single source of truth for the academic structure of a
course. It converts raw syllabus text into a CanonicalSyllabus:

    course metadata
    -> units
    -> unit titles
    -> ordered topics
    -> official / derived hours
    -> course objectives
    -> course outcomes
    -> textbooks
    -> references

The parser never asks an AI model to decide academic structure.

Important ownership rules
-------------------------
* Unit titles and topics come from the syllabus.
* Unit hours printed in the syllabus are authoritative.
* Topic hours are derived from the authoritative unit hours when the syllabus
  does not explicitly assign hours to individual topics.
* A printed TOTAL is authoritative when present.
* Missing values are marked as ``default`` or ``derived`` rather than being
  silently presented as syllabus facts.
* Topic ids are stable: ``U{unit}-T{order}``.
"""

from __future__ import annotations

import re

from app.schemas.syllabus_schema import (
    CanonicalOutcome,
    CanonicalSyllabus,
    CanonicalTopic,
    CanonicalUnit,
)


class SyllabusParseError(Exception):
    """Raised when the syllabus cannot be safely parsed."""

    def __init__(self, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_DASHES = dict.fromkeys(
    map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015"),
    "-",
)

_QUOTES = {
    ord("\u2018"): "'",
    ord("\u2019"): "'",
    ord("\u201c"): '"',
    ord("\u201d"): '"',
    ord("\u00a0"): " ",
    ord("\u2022"): "*",
}

_TRANSLATION = {**_DASHES, **_QUOTES}


_PAGE_ARTIFACT_RE = re.compile(
    r"^\s*(?:page\s*\d+(?:\s*of\s*\d+)?|[-–—\s]*\d{1,3}[-–—\s]*)\s*$",
    re.IGNORECASE,
)


_LTPC_HEADER_RE = re.compile(
    r"^\s*L\s*[:\s]\s*T\s*[:\s]\s*P\s*[:\s]\s*C\s*$",
    re.IGNORECASE,
)


_LTPC_ROW_RE = re.compile(
    r"^\s*\d+\s+\d+\s+\d+\s+\d+\s*$"
)


def normalize_text(text: str) -> str:
    """Normalize whitespace and common PDF/DOCX punctuation.

    Line structure is deliberately preserved because the syllabus parser
    relies on headings and section boundaries.
    """
    if not text:
        return ""

    cleaned = (
        str(text)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .translate(_TRANSLATION)
    )

    lines: list[str] = []

    for raw in cleaned.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw).strip()

        if not line:
            lines.append("")
            continue

        if _PAGE_ARTIFACT_RE.match(line):
            continue

        if _LTPC_HEADER_RE.match(line):
            continue

        if _LTPC_ROW_RE.match(line):
            continue

        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Unit parsing
# ---------------------------------------------------------------------------

_ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
}


_UNIT_RE = re.compile(
    r"^UNIT\s*[-:.]?\s*(?P<num>[IVXLC]{1,7}|\d{1,2})\b(?P<rest>.*)$",
    re.IGNORECASE,
)


_HEADER_HOURS_RE = re.compile(
    r"(?:^|[\s\(\[])(?P<hours>\d{1,3})"
    r"\s*(?:hours?|hrs?\.?|periods?)?"
    r"\s*[\)\]]?\s*$",
    re.IGNORECASE,
)


_HEADER_HOURS_LABELLED_RE = re.compile(
    r"(?:^|[\s\(\[])(?P<hours>\d{1,3}(?:\.\d+)?)"
    r"\s*(?:hours?|hrs?\.?|periods?)"
    r"\s*[\)\]]?\s*$",
    re.IGNORECASE,
)


_EXPLICIT_HOURS_RE = re.compile(
    r"[\(\[]?\s*(?P<hours>\d{1,3}(?:\.\d+)?)"
    r"\s*(?:hours?|hrs?\.?|periods?)"
    r"\s*[\)\]]?",
    re.IGNORECASE,
)


_TOTAL_HOURS_RE = re.compile(
    r"^TOTAL\s*[:\-]?\s*"
    r"(?P<hours>\d{1,3}(?:\.\d+)?)"
    r"\s*(?:hours?|hrs?\.?|periods?)?"
    r"\s*$",
    re.IGNORECASE,
)


def roman_to_int(value: str) -> int | None:
    """Convert a Roman numeral to an integer."""
    text = (value or "").strip().upper()

    if not text:
        return None

    if any(char not in _ROMAN_VALUES for char in text):
        return None

    total = 0
    previous = 0

    for char in reversed(text):
        current = _ROMAN_VALUES[char]

        if current < previous:
            total -= current
        else:
            total += current

        previous = max(previous, current)

    return total or None


def _unit_number(token: str) -> int | None:
    token = (token or "").strip()

    if token.isdigit():
        number = int(token)
        return number if number >= 1 else None

    return roman_to_int(token)


def match_unit_header(
    line: str,
) -> tuple[int, str, float | None] | None:
    """Parse a unit header.

    Examples:

        UNIT I PROBLEM SOLVING 9
        UNIT II PROBABILISTIC REASONING 9
        UNIT III SEARCH STRATEGIES (9 PERIODS)

    Returns:

        (unit_number, unit_title, hours)

    ``hours`` is ``None`` when no unit-hour value is printed.
    """
    match = _UNIT_RE.match((line or "").strip())

    if not match:
        return None

    number = _unit_number(match.group("num"))

    if number is None:
        return None

    rest = (match.group("rest") or "").strip(" -:\t")

    hours: float | None = None

    labelled = _HEADER_HOURS_LABELLED_RE.search(rest)
    bare = _HEADER_HOURS_RE.search(rest)

    hours_match = labelled or bare

    if hours_match:
        try:
            hours = float(hours_match.group("hours"))
        except (TypeError, ValueError):
            hours = None

        if hours is not None:
            rest = rest[: hours_match.start()].rstrip(
                " -(:[\t"
            )

    title = re.sub(r"\s+", " ", rest).strip(
        " -:.\t"
    )

    return number, title, hours


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

_SECTION_RES: list[tuple[str, re.Pattern]] = [
    (
        "textbooks",
        re.compile(
            r"^TEXT\s*-?\s*BOOKS?\b|^TEXTBOOKS?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "references",
        re.compile(
            r"^REFERENCES?\b|^REFERENCE\s*-?\s*BOOKS?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "outcomes",
        re.compile(
            r"^(?:COURSE\s+)?OUTCOMES?\b"
            r"|^COURSE\s+OUTCOMES?\s*[:\-]?"
            r"|^CO\s*[-:]?\s*PO\b"
            r"|^(?:CO|PO)\s+MAPPING\b"
            r"|^MAPPING\s+OF\b",
            re.IGNORECASE,
        ),
    ),
    (
        "objectives",
        re.compile(
            r"^(?:COURSE\s+)?OBJECTIVES?\b"
            r"|^PRE\s*-?\s*REQUISITES?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "practical",
        re.compile(
            r"^(?:LIST\s+OF\s+)?EXPERIMENTS?\b"
            r"|^PRACTICAL\b"
            r"|^LAB(?:ORATORY)?\s+"
            r"(?:COMPONENT|EXERCISES?)\b",
            re.IGNORECASE,
        ),
    ),
]


def _match_section(line: str) -> str | None:
    stripped = (
        (line or "")
        .strip()
        .lstrip("*0123456789.) ")
        .strip()
    )

    for name, pattern in _SECTION_RES:
        if pattern.match(stripped):
            return name

    return None


# ---------------------------------------------------------------------------
# Topic extraction
# ---------------------------------------------------------------------------

_TOPIC_NOISE = {
    "and",
    "etc",
    "etc.",
    "its",
    "the",
    "to",
    "unit",
    "contd",
    "contd.",
    "continued",
    "nil",
    "none",
}


_MIN_TOPIC_LENGTH = 3


_LEADING_MARKER_RE = re.compile(
    r"^(?:[*\-•]+|\d{1,2}[.)]|\([a-z0-9]{1,3}\))\s*"
)


def _strip_markers(line: str) -> str:
    return _LEADING_MARKER_RE.sub(
        "",
        (line or "").strip(),
    ).strip()


def _is_noise_fragment(fragment: str) -> bool:
    text = (
        fragment
        .strip()
        .strip(".;:-")
        .strip()
    )

    if not text:
        return True

    if text.lower() in _TOPIC_NOISE:
        return True

    if len(text) < _MIN_TOPIC_LENGTH:
        return True

    if re.fullmatch(r"[\d\s.:%-]+", text):
        return True

    if _unit_number(text) is not None and len(text) <= 4:
        return True

    if not re.search(r"[A-Za-z]", text):
        return True

    return False


def extract_topics_from_body(
    lines: list[str],
) -> list[str]:
    """Extract ordered topics from a unit body.

    Supports:

        Topic A
        Topic B
        Topic C

    and:

        Topic A, Topic B, Topic C

    The syllabus order is preserved.
    """
    topics: list[str] = []

    for raw in lines:
        line = _strip_markers(raw)

        if not line:
            continue

        # Remove explicitly labelled hour annotations.
        line = _EXPLICIT_HOURS_RE.sub(
            " ",
            line,
        )

        line = re.sub(
            r"\s+",
            " ",
            line,
        ).strip()

        if not line:
            continue

        fragments = re.split(
            r"[,;]|(?<=[a-z])\.\s+(?=[A-Z])",
            line,
        )

        for fragment in fragments:
            if fragment is None:
                continue

            candidate = (
                fragment
                .strip()
                .strip("*-•")
                .strip()
            )

            candidate = candidate.rstrip(
                ".;: "
            ).strip()

            if _is_noise_fragment(candidate):
                continue

            topics.append(
                re.sub(
                    r"\s+",
                    " ",
                    candidate,
                )
            )

    return topics


# ---------------------------------------------------------------------------
# Hours
# ---------------------------------------------------------------------------

def distribute_hours(
    total_hours: float,
    count: int,
) -> list[float]:
    """Distribute hours across topics without losing total teaching time.

    The split is performed in minutes, making the result deterministic.

    Example:

        9 hours / 4 topics

        -> 2.25, 2.25, 2.25, 2.25

    Example:

        10 hours / 3 topics

        -> 3.3333, 3.3333, 3.3334

    The values are derived values, not claims that the syllabus individually
    assigned those hours to each topic.
    """
    if count <= 0:
        return []

    total_minutes = int(
        round(float(total_hours) * 60)
    )

    if total_minutes <= 0:
        return [0.0] * count

    base, remainder = divmod(
        total_minutes,
        count,
    )

    minutes = [
        base + (1 if index < remainder else 0)
        for index in range(count)
    ]

    return [
        round(value / 60, 4)
        for value in minutes
    ]


# ---------------------------------------------------------------------------
# Outcomes / references
# ---------------------------------------------------------------------------

_NUMBERED_ITEM_RE = re.compile(
    r"^\s*(\d{1,2})[.)]\s*(.+)$"
)


_OUTCOME_RE = re.compile(
    r"^\s*"
    r"(?P<id>(?:CO|C\.?O\.?)\s*[-]?\s*\d{1,2})"
    r"\s*[:.\-)]?\s*"
    r"(?P<desc>.*)$",
    re.IGNORECASE,
)


def _collect_numbered_entries(
    lines: list[str],
) -> list[str]:
    """Collect numbered references/objectives with wrapped lines."""
    entries: list[str] = []
    current: list[str] = []

    for raw in lines:
        line = (raw or "").strip()

        if not line:
            continue

        numbered = _NUMBERED_ITEM_RE.match(line)

        if numbered:
            if current:
                entries.append(
                    " ".join(current).strip()
                )

            current = [
                numbered.group(2).strip()
            ]

        elif current:
            current.append(line)

        else:
            current = [
                _strip_markers(line)
            ]

    if current:
        entries.append(
            " ".join(current).strip()
        )

    return [
        re.sub(
            r"\s+",
            " ",
            entry,
        ).strip(" .;")
        for entry in entries
        if entry.strip(" .;")
    ]


def _collect_outcomes(
    lines: list[str],
) -> list[CanonicalOutcome]:
    outcomes: list[CanonicalOutcome] = []

    current: CanonicalOutcome | None = None

    for raw in lines:
        line = _strip_markers(raw)

        if not line:
            continue

        match = _OUTCOME_RE.match(line)

        if match:
            if current is not None:
                outcomes.append(current)

            outcome_id = re.sub(
                r"[\s.\-]",
                "",
                match.group("id"),
            ).upper()

            current = CanonicalOutcome(
                outcome_id=outcome_id,
                description=re.sub(
                    r"\s+",
                    " ",
                    match.group("desc"),
                ).strip(),
            )

        elif current is not None:
            current = CanonicalOutcome(
                outcome_id=current.outcome_id,
                description=re.sub(
                    r"\s+",
                    " ",
                    f"{current.description} {line}",
                ).strip(),
            )

    if current is not None:
        outcomes.append(current)

    seen: dict[str, CanonicalOutcome] = {}

    for outcome in outcomes:
        existing = seen.get(
            outcome.outcome_id
        )

        if (
            existing is None
            or len(outcome.description)
            > len(existing.description)
        ):
            seen[outcome.outcome_id] = outcome

    return [
        seen[key]
        for key in sorted(
            seen,
            key=lambda value: (
                len(value),
                value,
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Course metadata
# ---------------------------------------------------------------------------

_COURSE_CODE_RE = re.compile(
    r"^(?P<code>[A-Z]{2,4}\s?\d{3,5}[A-Z]?)"
    r"\s*[-:]?\s*"
    r"(?P<title>[A-Za-z].*)?$"
)


def _parse_course_header(
    preamble: list[str],
) -> tuple[str | None, str | None]:
    """Recover course code and title from the preamble."""
    for raw in preamble:
        line = (raw or "").strip()

        if not line or _match_section(line):
            continue

        match = _COURSE_CODE_RE.match(line)

        if not match:
            continue

        code = re.sub(
            r"\s+",
            "",
            match.group("code"),
        ).upper()

        title = (
            match.group("title") or ""
        ).strip(" -:.")

        title = re.sub(
            r"\s+",
            " ",
            title,
        )

        return code, title or None

    # Fallback: first substantial preamble line.
    for raw in preamble:
        line = (raw or "").strip()

        if (
            line
            and not _match_section(line)
            and len(line) > 4
        ):
            return (
                None,
                re.sub(
                    r"\s+",
                    " ",
                    line,
                ).strip(" -:."),
            )

    return None, None


# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------

def parse_syllabus(
    text: str,
) -> CanonicalSyllabus:
    """Parse raw syllabus text into a CanonicalSyllabus.

    The parser refuses to produce a syllabus when it cannot recover at least
    one topic for every detected unit.
    """
    normalized = normalize_text(text)

    if not normalized.strip():
        raise SyllabusParseError(
            "The syllabus document is empty, so its structure could not be parsed.",
            {
                "units_found": 0,
                "topics_found": 0,
                "sections_found": [],
            },
        )

    lines = normalized.split("\n")

    preamble: list[str] = []

    unit_headers: list[
        tuple[int, str, float | None]
    ] = []

    unit_bodies: list[list[str]] = []

    sections: dict[str, list[str]] = {}

    total_hours: float | None = None

    current_unit: int | None = None
    current_section: str | None = None

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        # ---------------------------------------------------------------
        # TOTAL hours
        # ---------------------------------------------------------------
        total_match = _TOTAL_HOURS_RE.match(
            stripped
        )

        if total_match:
            try:
                total_hours = float(
                    total_match.group("hours")
                )
            except (
                TypeError,
                ValueError,
            ):
                total_hours = None

            current_unit = None
            current_section = None
            continue

        # ---------------------------------------------------------------
        # UNIT header
        # ---------------------------------------------------------------
        header = match_unit_header(
            stripped
        )

        if header is not None:
            unit_headers.append(header)
            unit_bodies.append([])

            current_unit = (
                len(unit_bodies) - 1
            )

            current_section = None
            continue

        # ---------------------------------------------------------------
        # Section header
        # ---------------------------------------------------------------
        section = _match_section(
            stripped
        )

        if section is not None:
            current_section = section
            sections.setdefault(
                section,
                [],
            )

            current_unit = None

            # Example:
            # TEXT BOOKS: 1. Russell & Norvig ...
            remainder = re.split(
                r"[:\-]",
                stripped,
                maxsplit=1,
            )

            if (
                len(remainder) == 2
                and remainder[1].strip()
            ):
                sections[section].append(
                    remainder[1].strip()
                )

            continue

        # ---------------------------------------------------------------
        # Current unit body
        # ---------------------------------------------------------------
        if current_unit is not None:
            unit_bodies[
                current_unit
            ].append(stripped)

        # ---------------------------------------------------------------
        # Current named section
        # ---------------------------------------------------------------
        elif current_section is not None:
            sections[
                current_section
            ].append(stripped)

        # ---------------------------------------------------------------
        # Preamble
        # ---------------------------------------------------------------
        else:
            preamble.append(stripped)

    diagnostics = {
        "units_found": len(unit_headers),
        "sections_found": sorted(
            sections.keys()
        ),
        "lines_scanned": len(
            [
                line
                for line in lines
                if line.strip()
            ]
        ),
    }

    if not unit_headers:
        raise SyllabusParseError(
            "No syllabus units could be identified in this document. "
            "Expected unit headings such as 'UNIT I <title> 9'.",
            diagnostics,
        )

    # -------------------------------------------------------------------
    # Build canonical units
    # -------------------------------------------------------------------

    units: list[CanonicalUnit] = []
    empty_units: list[int] = []

    for index, (
        number,
        title,
        header_hours,
    ) in enumerate(unit_headers):
        body = unit_bodies[index]

        topic_names = extract_topics_from_body(
            body
        )

        hours = header_hours

        hours_source = (
            "syllabus"
            if hours is not None
            else "default"
        )

        # ---------------------------------------------------------------
        # If the unit header has no hours, look for an explicitly labelled
        # hour figure inside its body.
        # ---------------------------------------------------------------
        if hours is None:
            for raw in body:
                inline = _EXPLICIT_HOURS_RE.search(
                    raw
                )

                if not inline:
                    continue

                try:
                    hours = float(
                        inline.group("hours")
                    )
                    hours_source = "syllabus"
                except (
                    TypeError,
                    ValueError,
                ):
                    hours = None

                break

        if not topic_names:
            empty_units.append(number)

        units.append(
            CanonicalUnit(
                unit_number=number,
                unit_title=title,
                hours=hours,
                hours_source=hours_source,
                topics=[],
            )
        )

        # Create topics after unit validation so topic-hour allocation can
        # use the final unit-hour value.
        for order, name in enumerate(
            topic_names,
            start=1,
        ):
            units[-1].topics.append(
                CanonicalTopic(
                    topic_id=f"U{number}-T{order}",
                    topic=name,
                    unit_number=number,
                    order=order,
                    hours=0.0,
                    hours_source="default",
                )
            )

    diagnostics["topics_found"] = sum(
        len(unit.topics)
        for unit in units
    )

    diagnostics["units_without_topics"] = (
        empty_units
    )

    if empty_units:
        raise SyllabusParseError(
            "The syllabus structure could not be parsed: "
            "no topics were found for unit(s) "
            f"{', '.join(str(n) for n in empty_units)}.",
            diagnostics,
        )

    # -------------------------------------------------------------------
    # Resolve missing unit hours
    # -------------------------------------------------------------------

    total_hours_source = (
        "syllabus"
        if total_hours is not None
        else "default"
    )

    units_missing_hours = [
        unit
        for unit in units
        if unit.hours is None
    ]

    if (
        units_missing_hours
        and total_hours is not None
    ):
        accounted = sum(
            float(unit.hours or 0)
            for unit in units
            if unit.hours is not None
        )

        remaining = max(
            float(total_hours)
            - accounted,
            0.0,
        )

        derived = distribute_hours(
            remaining,
            len(units_missing_hours),
        )

        for unit, value in zip(
            units_missing_hours,
            derived,
        ):
            unit.hours = value
            unit.hours_source = "derived"

    # If every unit has an authoritative hour value but no printed total,
    # calculate the total as derived information.
    if total_hours is None:
        stated = [
            unit.hours
            for unit in units
            if unit.hours is not None
        ]

        if (
            stated
            and len(stated) == len(units)
        ):
            total_hours = round(
                sum(stated),
                2,
            )
            total_hours_source = "derived"

    # -------------------------------------------------------------------
    # Topic-hour allocation
    # -------------------------------------------------------------------
    #
    # IMPORTANT:
    #
    # Topic hours are NOT treated as independently printed syllabus facts
    # unless the parser explicitly supports a topic-hour syntax.
    #
    # When a unit says:
    #
    #     UNIT I PROBLEM SOLVING 9
    #
    # and contains 6 topics, the canonical representation derives the
    # 9 teaching hours across those 6 topics.
    #
    # This keeps:
    #
    #     sum(topic.hours) == unit.hours
    #
    # while clearly marking topic hours as "derived".
    #
    # The scheduler can therefore use topic.hours as its exact required
    # teaching capacity without destroying the authoritative unit total.
    # -------------------------------------------------------------------

    for unit in units:
        topic_count = len(unit.topics)

        if (
            unit.hours is not None
            and unit.hours > 0
        ):
            topic_hours = distribute_hours(
                unit.hours,
                topic_count,
            )

            for topic, value in zip(
                unit.topics,
                topic_hours,
            ):
                topic.hours = value
                topic.hours_source = "derived"

        else:
            # No hour information exists for this unit.
            #
            # We retain a neutral 1-hour topic capacity but explicitly mark
            # it as default. This is NOT represented as syllabus-authoritative
            # data.
            for topic in unit.topics:
                topic.hours = 1.0
                topic.hours_source = "default"

    # -------------------------------------------------------------------
    # Course metadata
    # -------------------------------------------------------------------

    course_code, course_title = (
        _parse_course_header(
            preamble
        )
    )

    return CanonicalSyllabus(
        course_code=course_code,
        course_title=course_title,
        units=units,
        course_objectives=_collect_numbered_entries(
            sections.get(
                "objectives",
                [],
            )
        ),
        course_outcomes=_collect_outcomes(
            sections.get(
                "outcomes",
                [],
            )
        ),
        textbooks=_collect_numbered_entries(
            sections.get(
                "textbooks",
                [],
            )
        ),
        references=_collect_numbered_entries(
            sections.get(
                "references",
                [],
            )
        ),
        total_hours=total_hours,
        total_hours_source=total_hours_source,
    )