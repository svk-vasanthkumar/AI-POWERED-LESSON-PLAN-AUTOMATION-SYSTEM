import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config.settings import settings

async def main():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.DATABASE_NAME]
    
    cursor = db.academic_calendar.find().sort("_id", -1).limit(1)
    async for doc in cursor:
        print("=== Academic Calendar ===")
        print("academic_year:", doc.get("academic_year"))
        print("semester:", doc.get("semester"))
        print("status:", doc.get("status"))
        print("cia_1:", doc.get("cia_1"))
        print("cia_2:", doc.get("cia_2"))
        print("cia_3:", doc.get("cia_3"))
        print("model_theory:", doc.get("model_theory"))
        print("model_practical:", doc.get("model_practical"))
        print("semester_end_theory:", doc.get("semester_end_theory"))
        print("semester_end_practical:", doc.get("semester_end_practical"))
        print("winter_vacation:", doc.get("winter_vacation"))
        print("semester_start:", doc.get("semester_start"))
        print("semester_end:", doc.get("semester_end"))

if __name__ == "__main__":
    asyncio.run(main())
