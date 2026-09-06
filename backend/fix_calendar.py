import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
async def fix_calendar():
    client = AsyncIOMotorClient(os.getenv('MONGODB_URI'))
    db = client[os.getenv('DATABASE_NAME')]
    cursor = db.academic_calendar.find().sort('_id', -1).limit(1)
    ac = await cursor.to_list(length=1)
    if not ac: return
    ac = ac[0]
    events = ac.get('events', [])
    updated = False
    for ev in events:
        if ev.get('is_holiday') and (not ev.get('description') or ev.get('description').strip() == ''):
            ev['is_holiday'] = False
            updated = True
            print('Fixed holiday status for', ev.get('date') or ev.get('start_date'))
    if updated:
        await db.academic_calendar.update_one({'_id': ac['_id']}, {'$set': {'events': events}})
        print('Calendar updated!')

asyncio.run(fix_calendar())
