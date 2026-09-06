import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

async def fix_timetable():
    client = AsyncIOMotorClient(os.getenv('MONGODB_URI'))
    db = client[os.getenv('DATABASE_NAME')]
    cursor = db.timetables.find().sort('_id', -1).limit(1)
    tt = await cursor.to_list(length=1)
    if not tt: return
    tt = tt[0]
    schedule = tt.get('schedule', [])
    updated = False
    for slot in schedule:
        if slot.get('day') == 'Tuesday' and slot.get('subject') == 'MAD' and slot.get('period_start') == 1 and slot.get('period_end') == 1:
            slot['period_end'] = 2
            updated = True
            print('Fixed Tuesday MAD to span Hour 1 and 2')
    if updated:
        await db.timetables.update_one({'_id': tt['_id']}, {'$set': {'schedule': schedule}})
        print('Timetable updated in database!')

asyncio.run(fix_timetable())
