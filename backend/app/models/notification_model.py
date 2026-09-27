from datetime import datetime, UTC
from bson import ObjectId

def create_notification_document(
    user_id: ObjectId,
    title: str,
    message: str,
    type: str = "info",
    link: str | None = None,
    actor_id: str | None = None,
    actor_name: str | None = None,
    event_type: str = "GENERAL",
    entity_type: str = "GENERAL",
    entity_id: str | None = None,
    course_id: str | None = None,
    severity: str = "INFO",
    email_subject: str | None = None,
    metadata: dict | None = None,
):
    """Creates a standardized dictionary structure for MongoDB notification insertion."""
    doc = {
        "user_id": user_id,
        "recipient_id": str(user_id),
        "actor_id": str(actor_id) if actor_id else None,
        "actor_name": actor_name or "System",
        "title": title,
        "message": message,
        "type": type.lower(),
        "event_type": event_type.upper(),
        "entity_type": entity_type.upper(),
        "entity_id": str(entity_id) if entity_id else None,
        "course_id": str(course_id) if course_id else None,
        "severity": severity.upper(),
        "read": False,
        "email_subject": email_subject or title,
        "email_sent": False,
        "email_sent_at": None,
        "email_error": None,
        "metadata": metadata or {},
        "created_at": datetime.now(UTC),
    }
    if link:
        doc["link"] = link
    return doc

