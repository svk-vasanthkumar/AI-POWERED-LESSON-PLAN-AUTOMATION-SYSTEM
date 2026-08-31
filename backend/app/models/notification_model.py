from datetime import datetime, UTC
from bson import ObjectId

def create_notification_document(
    user_id: ObjectId,
    title: str,
    message: str,
    type: str = "info",
):
    """Creates a standardized dictionary structure for MongoDB notification insertion."""
    return {
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": type,
        "read": False,
        "created_at": datetime.now(UTC),
    }
