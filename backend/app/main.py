from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config.settings import settings
from app.database.mongodb import connect_to_mongo, close_mongo_connection


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