import asyncio
import os
import json
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

load_dotenv()

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

async def query_db():
    client = AsyncIOMotorClient(os.getenv('MONGODB_URI'))
    db = client[os.getenv('DATABASE_NAME')]
    
    print("--- CALENDAR ---")
    cursor = db.academic_calendars.find().sort('_id', -1).limit(1)
    ac = await cursor.to_list(length=1)
    if ac:
        print(json.dumps(ac[0].get('events', []), cls=CustomJSONEncoder, indent=2))
        print("Working days:", ac[0].get('working_days', []))
    
    print("--- TIMETABLE ---")
    cursor = db.timetables.find().sort('_id', -1).limit(1)
    tt = await cursor.to_list(length=1)
    if tt:
        for slot in tt[0].get('schedule', []):
            if slot.get('subject') == 'MAD':
                print(slot)

asyncio.run(query_db())
