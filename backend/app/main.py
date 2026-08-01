from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.faculty import router as faculty_router
from app.api.v1.lesson_plan import router as lesson_router
from app.api.v1.syllabus import router as syllabus_router
from app.config.settings import settings
from app.core.exception import register_exception_handlers
from app.database.mongodb import close_mongo_connection, connect_to_mongo
from app.middleware.logging import log_requests
from app.api.v1.course import router as course_router
from app.api.v1.academic_calendar import router as calendar_router




@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
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



@app.get("/")
async def root():
    return {"message": "Welcome to AI Lesson Plan Automation API"}


@app.get("/health")
async def health():
    return {"status": "OK"}