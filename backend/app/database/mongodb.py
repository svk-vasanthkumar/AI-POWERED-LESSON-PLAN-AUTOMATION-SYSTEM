from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError

from app.config.logger import logger
from app.config.settings import settings

client = None
database = None


class DatabaseUnavailableError(RuntimeError):
    """Raised when MongoDB cannot be reached / verified at startup.

    Constructing an ``AsyncIOMotorClient`` is lazy and never proves the server
    is reachable, so startup pings the server explicitly and raises this on
    failure instead of letting the app come up in a falsely-"connected" state.
    """


async def connect_to_mongo():
    """Create the Mongo client, verify connectivity, and ensure indexes.

    A freshly-constructed ``AsyncIOMotorClient`` does NOT open a connection, so
    we issue a lightweight ``ping`` to confirm the server is actually reachable
    before reporting success. Only after a successful ping do we create the
    data-integrity indexes.
    """
    global client, database

    client = AsyncIOMotorClient(settings.MONGODB_URI)
    database = client[settings.DATABASE_NAME]

    # Verify connectivity with a lightweight ping — never assume "connected"
    # just because the client object exists.
    await ping_database(client)

    # Ensure the data-integrity indexes exist. This is idempotent, so it is
    # safe to run on every startup / connection.
    await init_indexes(database)

    logger.info("Connected to MongoDB (database=%s)", settings.DATABASE_NAME)


async def ping_database(mongo_client=None) -> bool:
    """Ping the MongoDB server to verify it is actually reachable.

    Returns ``True`` on success. Raises :class:`DatabaseUnavailableError` when
    the server cannot be reached, with a safe message (driver internals are
    logged server-side only, never surfaced).
    """
    mongo_client = mongo_client or client
    if mongo_client is None:
        raise DatabaseUnavailableError("Database client is not initialised")

    try:
        await mongo_client.admin.command("ping")
    except PyMongoError as exc:
        logger.exception("MongoDB ping failed")
        raise DatabaseUnavailableError("Could not reach the database") from exc
    return True


async def close_mongo_connection():
    global client

    if client:
        client.close()
        logger.info("MongoDB connection closed")


def get_database():
    return database


# Each index is (collection, keys, name). Keys is a single field name or a list
# of (field, direction) tuples for a compound index. Names are stable/explicit
# so repeated initialization never produces conflicting auto-generated names.
_UNIQUE_INDEXES = (
    ("users", "email", "uniq_users_email"),
    ("faculty", "faculty_id", "uniq_faculty_faculty_id"),
    (
        "academic_calendar",
        [("academic_year", 1), ("semester", 1)],
        "uniq_calendar_year_semester",
    ),
)

# Non-unique LOOKUP indexes for the hot, non-``_id`` query paths exercised on
# every request by a shared faculty pool. These must NOT be unique: a course
# legitimately has many schedules (versioned) and a faculty many courses.
#
# Justification (one entry per real query in the codebase):
#   courses.faculty_id            -> accessible_course_ids(), run on EVERY
#                                    authorization check (auth/resource_access)
#   generated_schedules
#     (lesson_plan_id, active)    -> planned date/period lookup for a lesson
#                                    plan (the original "dates not shown" path)
#     (course_id, active, version)-> active-schedule lookup + supersede on
#                                    regeneration, and progress resolution
#   lesson_plans.course_id        -> lesson-plan listing / schedule linking
#   syllabi.course_id             -> syllabus listing per course
#   timetables.(faculty_id, ...)  -> timetable resolution during scheduling
#   faculty.user_id               -> resolves the logged-in user to a faculty
_LOOKUP_INDEXES = (
    ("courses", [("faculty_id", 1)], "idx_courses_faculty_id"),
    (
        "generated_schedules",
        [("lesson_plan_id", 1), ("active", 1)],
        "idx_schedules_lesson_plan_active",
    ),
    (
        "generated_schedules",
        [("course_id", 1), ("active", 1), ("version", -1)],
        "idx_schedules_course_active_version",
    ),
    ("lesson_plans", [("course_id", 1)], "idx_lesson_plans_course_id"),
    ("syllabi", [("course_id", 1)], "idx_syllabi_course_id"),
    (
        "timetables",
        [("faculty_id", 1), ("semester", 1), ("academic_year", 1)],
        "idx_timetables_faculty_sem_year",
    ),
    ("faculty", [("user_id", 1)], "idx_faculty_user_id"),
)


async def init_indexes(db=None):
    """Create the integrity (unique) and performance (lookup) indexes.

    Indexes created:
      - ``users.email``                       -> unique
      - ``faculty.faculty_id``                -> unique
      - ``academic_calendar``                 -> unique compound
                                                 (academic_year + semester)
      - plus the non-unique lookup indexes in ``_LOOKUP_INDEXES`` covering the
        hot non-``_id`` queries (authorization by faculty, active-schedule and
        lesson-plan resolution, timetable lookup).


    ``create_index`` is idempotent: MongoDB is a no-op when an identical index
    already exists, so calling this function multiple times is safe. Each index
    is given a stable, explicit name so repeated initialization never produces
    conflicting auto-generated names.

    If pre-existing DUPLICATE data would violate a new unique index, MongoDB
    refuses to build it. We surface that as a clear, controlled error (with the
    offending index logged) rather than silently deleting records — destructive
    data migration is never performed automatically.
    """
    if db is None:
        db = database

    if db is None:
        raise RuntimeError(
            "init_indexes called before the database connection was created"
        )

    for collection_name, keys, name in _UNIQUE_INDEXES:
        try:
            await db[collection_name].create_index(keys, unique=True, name=name)
            logger.debug("Ensured unique index %s on %s", name, collection_name)
        except (DuplicateKeyError, OperationFailure) as exc:
            # Duplicate legacy data prevents building a unique index. Fail
            # clearly instead of deleting records to force the index through.
            logger.error(
                "Failed to create unique index %s on %s (duplicate data?): %s",
                name,
                collection_name,
                exc,
            )
            raise RuntimeError(
                f"Cannot create unique index '{name}' on '{collection_name}': "
                "duplicate records exist. Resolve the duplicates before starting."
            ) from exc

    # Lookup indexes are a PERFORMANCE optimization, never an integrity
    # constraint, so a failure here must not prevent the app from starting.
    # They are non-unique by design: many schedules per course, many courses
    # per faculty.
    created_lookups = 0
    for collection_name, keys, name in _LOOKUP_INDEXES:
        try:
            await db[collection_name].create_index(keys, name=name)
            created_lookups += 1
            logger.debug("Ensured lookup index %s on %s", name, collection_name)
        except OperationFailure as exc:
            logger.warning(
                "Could not create lookup index %s on %s (queries still "
                "correct, just unindexed): %s",
                name,
                collection_name,
                exc,
            )

    logger.info(
        "Database indexes ensured (%d unique, %d/%d lookup)",
        len(_UNIQUE_INDEXES),
        created_lookups,
        len(_LOOKUP_INDEXES),
    )
