from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import router as auth_router
from app.api.v1.faculty import router as faculty_router
from app.api.v1.lesson_plan import router as lesson_router
from app.api.v1.syllabus import router as syllabus_router
from app.config.settings import settings
from app.core.exception import register_exception_handlers
from app.core.limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.database.mongodb import (
    DatabaseUnavailableError,
    close_mongo_connection,
    connect_to_mongo,
    ping_database,
)
from app.middleware.logging import log_requests
from app.api.v1.course import router as course_router
from app.api.v1.academic_calendar import router as calendar_router
from app.api.v1.timetable import router as timetable_router
from app.api.v1.scheduler import router as scheduler_router
from app.api.v1.reports import router as reports_router
from app.api.v1.notifications import router as notifications_router
from app.utils.timetable_periods import configure_period_times







@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_period_times({
        1: {"start_time": "09:00", "end_time": "09:50"},
        2: {"start_time": "09:50", "end_time": "10:40"},
        3: {"start_time": "11:00", "end_time": "11:50"},
        4: {"start_time": "11:50", "end_time": "12:40"},
        5: {"start_time": "13:30", "end_time": "14:20"},
        6: {"start_time": "14:20", "end_time": "15:10"},
        7: {"start_time": "15:10", "end_time": "16:00"},
    })
    await connect_to_mongo()

    # Migration: mark all existing users that were created before email-verification
    # was introduced as verified so they are not locked out.
    # This only updates documents that don't yet have the is_email_verified field.
    try:
        from app.database.mongodb import get_database
        db = get_database()
        result = await db.users.update_many(
            {"is_email_verified": {"$exists": False}},
            {"$set": {"is_email_verified": True, "auth_provider": "local"}}
        )
        if result.modified_count:
            print(f"[Migration] Marked {result.modified_count} existing user(s) as email-verified.")
    except Exception as e:
        print(f"[Migration Warning] Could not run email_verified migration: {e}")

    yield
    await close_mongo_connection()



app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS: allow only explicit frontend origins (never "*" with credentials).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Global Exception Handlers
register_exception_handlers(app)

# Rate Limiter Configuration
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include API Routers
app.include_router(auth_router)
app.include_router(lesson_router)
app.include_router(syllabus_router)
app.include_router(faculty_router)
app.middleware("http")(log_requests)
app.include_router(course_router)
app.include_router(calendar_router)
app.include_router(timetable_router)
app.include_router(scheduler_router)
app.include_router(reports_router)
app.include_router(notifications_router)


@app.get("/")
async def root():
    return {"message": "Welcome to AI Lesson Plan Automation API"}


@app.get("/health")
async def health():
    """Liveness + dependency readiness.

    The application process being up (liveness) is reported separately from
    the MongoDB dependency being reachable (readiness): a lightweight ping
    decides the database portion. When the database is unreachable the endpoint
    returns 503 with ``database: "unavailable"`` so orchestrators can tell a
    live-but-not-ready app from a healthy one. It never depends on Groq or OCR.
    """
    try:
        await ping_database()
        db_status = "connected"
    except DatabaseUnavailableError:
        # Already logged inside ping_database; do not leak driver internals.
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "unavailable"},
        )

    return {"status": "ok", "database": db_status}
