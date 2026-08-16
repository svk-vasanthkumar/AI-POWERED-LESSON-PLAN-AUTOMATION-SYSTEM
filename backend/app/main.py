from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.database import check_database_connection, close_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not await check_database_connection():
        raise RuntimeError("Database connection failed")

    yield

    await close_database()


app = FastAPI(
    title="Academic Lesson Plan System",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "message": "Academic Lesson Plan System API",
        "status": "running",
    }


@app.get("/health")
async def health():
    database_ok = await check_database_connection()

    if not database_ok:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )

    return {
        "status": "healthy",
        "database": "connected",
    }