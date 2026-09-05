import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.config.settings import settings

async def main():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.DATABASE_NAME]
    
    # Get the latest timetable
    cursor = db.timetables.find().sort("_id", -1).limit(1)
    async for doc in cursor:
        print("Status:", doc.get("status"))
        print("Schedule length:", len(doc.get("schedule", [])))
        print("Schedule:", doc.get("schedule"))
        print("Raw text:", doc.get("raw_text")[:100] if doc.get("raw_text") else None)
        print("Error/Exceptions:", doc.get("error"))

if __name__ == "__main__":
    asyncio.run(main())
