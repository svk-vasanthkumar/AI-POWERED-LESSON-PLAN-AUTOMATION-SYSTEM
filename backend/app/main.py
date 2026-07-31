from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.config.settings import settings
from app.database.mongodb import connect_to_mongo, close_mongo_connection
from app.api.v1.lesson_plan import router as lesson_router
from app.api.v1.syllabus import router as syllabus_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Include API Routers
app.include_router(auth_router)
app.include_router(lesson_router)
app.include_router(syllabus_router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to AI Lesson Plan Automation API"
    }


@app.get("/health")
async def health():
    return {
        "status": "OK"
    }