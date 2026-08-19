import os

from bson import ObjectId

from app.config.logger import logger
from app.database.mongodb import get_database
from app.models.syllabus_model import create_syllabus_document
from app.utils.object_id import to_object_id


class SyllabusInUseError(Exception):
    """Raised when a syllabus cannot be deleted because records depend on it.

    The API layer maps this to a controlled 409 CONFLICT. A syllabus that has
    generated lesson plans must not be deleted, because doing so would leave
    those lesson plans (and any schedule derived from them) pointing at a
    document — and an uploaded file — that no longer exists.
    """

    def __init__(self, dependencies: dict[str, int]):
        self.dependencies = dependencies
        summary = ", ".join(f"{count} {name}" for name, count in dependencies.items())
        super().__init__(
            "Syllabus cannot be deleted while it is referenced by other records "
            f"({summary}). Remove them first."
        )


def _id_variants(value) -> list:
    """Both ObjectId and string forms of an id (legacy-compatible queries)."""
    variants = [value, str(value)]
    if not isinstance(value, ObjectId):
        try:
            variants.append(ObjectId(str(value)))
        except Exception:
            pass
    seen: set = set()
    unique: list = []
    for item in variants:
        key = (type(item).__name__, str(item))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _serialize(doc: dict) -> dict:
    """Make a syllabus document JSON-serializable.

    Stringifies ``_id`` / ``course_id`` when stored as ObjectIds. The stored
    on-disk ``filepath`` is dropped from API responses so an internal
    filesystem path is never leaked to clients; ``filename`` /
    ``original_filename`` remain as display metadata.
    """
    if doc is None:
        return doc
    doc = dict(doc)
    if isinstance(doc.get("_id"), ObjectId):
        doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("course_id"), ObjectId):
        doc["course_id"] = str(doc["course_id"])
    doc.pop("filepath", None)
    return doc


async def save_syllabus(
    course_id: ObjectId,
    filename: str,
    filepath: str,
    extracted_text: str,
    original_filename: str | None = None,
    extraction_method: str = "text",
) -> str:
    db = get_database()

    document = create_syllabus_document(
        course_id=course_id,
        filename=filename,
        filepath=filepath,
        extracted_text=extracted_text,
        original_filename=original_filename,
        extraction_method=extraction_method,
    )

    result = await db.syllabi.insert_one(document)

    return str(result.inserted_id)


async def get_all_syllabi(
    course_id: str | None = None,
    scope_course_ids: list | None = None,
):
    """List syllabi.

    ``course_id`` optionally filters to a single course (frontend convenience).
    ``scope_course_ids`` restricts the result to a set of course ids for
    read-scoping (``None`` = no restriction / admin/hod; empty list = nothing).
    """
    db = get_database()

    query: dict = {}

    if scope_course_ids is not None:
        if not scope_course_ids:
            return []
        variants: list = []
        for cid in scope_course_ids:
            variants.extend(_id_variants(cid))
        query["course_id"] = {"$in": variants}

    if course_id is not None:
        course_oid = to_object_id(course_id, field="course_id")
        course_variants = _id_variants(course_oid)
        if "course_id" in query:
            allowed = {str(v) for v in query["course_id"]["$in"]}
            if not any(str(v) in allowed for v in course_variants):
                # Requested a course outside the caller's scope -> empty result.
                return []
        query["course_id"] = {"$in": course_variants}

    syllabi = []
    async for doc in db.syllabi.find(query):
        syllabi.append(_serialize(doc))
    return syllabi


async def get_syllabus(syllabus_id: str):
    """Return a single serialized syllabus, or ``None`` when not found."""
    db = get_database()
    syllabus_oid = to_object_id(syllabus_id, field="syllabus_id")

    doc = await db.syllabi.find_one({"_id": syllabus_oid})
    return _serialize(doc) if doc else None


async def get_syllabus_raw(syllabus_id: str):
    """Return the raw (unserialized) syllabus doc for internal auth checks."""
    db = get_database()
    syllabus_oid = to_object_id(syllabus_id, field="syllabus_id")
    return await db.syllabi.find_one({"_id": syllabus_oid})


def _remove_file_quietly(filepath: str | None) -> None:
    """Best-effort removal of the stored upload; failures are logged only."""
    if not filepath:
        return
    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
    except OSError:
        logger.exception("Failed to remove syllabus file on delete: %s", filepath)


async def delete_syllabus(syllabus_id: str) -> int:
    """Delete a syllabus and its stored file, refusing to orphan dependents.

    Raises :class:`SyllabusInUseError` (-> 409) when any lesson plan references
    the syllabus, so a generated lesson plan (and any schedule derived from it)
    is never left pointing at a deleted file. Returns the deleted count (0 ->
    404) otherwise. The on-disk file is removed only after the database record
    is deleted, so a misleading record is never left pointing at a missing file.
    """
    db = get_database()
    syllabus_oid = to_object_id(syllabus_id, field="syllabus_id")

    existing = await db.syllabi.find_one({"_id": syllabus_oid})
    if existing is None:
        return 0

    dependent_plans = await db.lesson_plans.count_documents(
        {"syllabus_id": {"$in": _id_variants(syllabus_oid)}}
    )
    if dependent_plans:
        raise SyllabusInUseError({"lesson plan(s)": dependent_plans})

    result = await db.syllabi.delete_one({"_id": syllabus_oid})
    if result.deleted_count:
        _remove_file_quietly(existing.get("filepath"))
    return result.deleted_count
