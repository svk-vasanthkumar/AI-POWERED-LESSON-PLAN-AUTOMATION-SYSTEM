from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings


client = AsyncIOMotorClient(
    settings.mongodb_uri,
    serverSelectionTimeoutMS=5000,
)

db = client[settings.database_name]


async def check_database_connection() -> bool:
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        return False


async def close_database():
    client.close()