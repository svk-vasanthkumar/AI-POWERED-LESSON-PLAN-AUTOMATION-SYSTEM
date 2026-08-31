from app.database.mongodb import get_database
from app.models.notification_model import create_notification_document
from app.utils.object_id import to_object_id

async def create_notification(user_id: str, title: str, message: str, type: str = "info") -> str:
    db = get_database()
    uid = to_object_id(user_id, field="user_id")
    doc = create_notification_document(uid, title, message, type)
    result = await db.notifications.insert_one(doc)
    return str(result.inserted_id)

async def get_user_notifications(user_id: str, limit: int = 50) -> list[dict]:
    db = get_database()
    uid = to_object_id(user_id, field="user_id")
    cursor = db.notifications.find({"user_id": uid}).sort("created_at", -1).limit(limit)
    
    results = []
    for doc in await cursor.to_list(length=limit):
        doc["_id"] = str(doc["_id"])
        doc["user_id"] = str(doc["user_id"])
        results.append(doc)
    return results

async def mark_as_read(notification_id: str, user_id: str) -> bool:
    db = get_database()
    nid = to_object_id(notification_id, field="notification_id")
    uid = to_object_id(user_id, field="user_id")
    result = await db.notifications.update_one(
        {"_id": nid, "user_id": uid},
        {"$set": {"read": True}}
    )
    return result.modified_count > 0

async def mark_all_as_read(user_id: str) -> int:
    db = get_database()
    uid = to_object_id(user_id, field="user_id")
    result = await db.notifications.update_many(
        {"user_id": uid, "read": False},
        {"$set": {"read": True}}
    )
    return result.modified_count
