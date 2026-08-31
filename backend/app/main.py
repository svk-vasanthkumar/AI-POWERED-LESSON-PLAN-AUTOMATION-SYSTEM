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
