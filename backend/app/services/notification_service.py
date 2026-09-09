import asyncio
import logging
from datetime import datetime, timedelta, UTC
from bson import ObjectId

from app.database.mongodb import get_database
from app.models.notification_model import create_notification_document
from app.utils.object_id import to_object_id
from app.services.email_service import send_event_notification_email

logger = logging.getLogger(__name__)


async def resolve_course_recipients(course_id: str, exclude_user_id: str | None = None) -> list[str]:
    """Identify user IDs of faculty assigned to a course and the department HOD."""
    db = get_database()
    recipients = set()
    
    try:
        cid = ObjectId(course_id) if ObjectId.is_valid(course_id) else course_id
        course = await db.courses.find_one({"_id": cid})
        if not course and isinstance(course_id, str):
            course = await db.courses.find_one({"id": course_id})
            
        if course:
            dept = course.get("department")
            # 1. HOD for department
            if dept:
                hod_user = await db.users.find_one({"department": dept, "role": "hod"})
                if hod_user:
                    recipients.add(str(hod_user["_id"]))
            
            # 2. Assigned faculty members
            raw_fids = course.get("faculty_ids") or []
            if not raw_fids and course.get("assigned_faculty_id"):
                raw_fids = [course.get("assigned_faculty_id")]
            if not raw_fids and course.get("faculty_id"):
                raw_fids = [course.get("faculty_id")]
                
            for fid in raw_fids:
                try:
                    f_oid = ObjectId(str(fid)) if ObjectId.is_valid(str(fid)) else fid
                    u_doc = await db.users.find_one({"_id": f_oid})
                    if u_doc:
                        recipients.add(str(u_doc["_id"]))
                    else:
                        f_doc = await db.faculty.find_one({"_id": f_oid})
                        if not f_doc:
                            f_doc = await db.faculty.find_one({"faculty_id": str(fid)})
                        if f_doc and f_doc.get("user_id"):
                            recipients.add(str(f_doc["user_id"]))
                        elif f_doc and f_doc.get("_id"):
                            recipients.add(str(f_doc["_id"]))
                except Exception as e:
                    logger.warning(f"Error resolving faculty recipient {fid}: {e}")
    except Exception as e:
        logger.error(f"Failed to resolve course recipients for {course_id}: {e}")
        
    if exclude_user_id:
        recipients.discard(str(exclude_user_id))
        
    return list(recipients)


async def resolve_department_hod(department: str, exclude_user_id: str | None = None) -> list[str]:
    """Find HOD user ID for a department."""
    db = get_database()
    recipients = set()
    if department:
        hod_user = await db.users.find_one({"department": department, "role": "hod"})
        if hod_user:
            recipients.add(str(hod_user["_id"]))
            
    if exclude_user_id:
        recipients.discard(str(exclude_user_id))
    return list(recipients)


async def dispatch_targeted_notification(
    recipient_id: str,
    title: str,
    message: str,
    actor_id: str | None = None,
    actor_name: str | None = "System",
    event_type: str = "GENERAL",
    entity_type: str = "GENERAL",
    entity_id: str | None = None,
    course_id: str | None = None,
    severity: str = "INFO",
    type: str = "info",
    link: str | None = None,
    email_subject: str | None = None,
    metadata: dict | None = None,
) -> str | None:
    """Core targeted notification dispatching engine with duplicate prevention & async email delivery."""
    db = get_database()
    
    # Do not notify the actor unless explicitly needed
    if actor_id and str(actor_id) == str(recipient_id) and event_type not in ["LESSON_PLAN_SUBMITTED_CONFIRMATION", "PASSWORD_RESET"]:
        return None
        
    try:
        uid = to_object_id(recipient_id, field="user_id")
    except Exception:
        logger.warning(f"Invalid recipient_id {recipient_id}")
        return None
        
    # Check 5-minute idempotency window to prevent duplicate alerts
    five_mins_ago = datetime.now(UTC) - timedelta(minutes=5)
    idempotency_query = {
        "user_id": uid,
        "event_type": event_type.upper(),
        "created_at": {"$gte": five_mins_ago}
    }
    if entity_id:
        idempotency_query["entity_id"] = str(entity_id)
        
    existing_duplicate = await db.notifications.find_one(idempotency_query)
    if existing_duplicate:
        logger.info(f"Prevented duplicate notification {event_type} for user {recipient_id}")
        return str(existing_duplicate["_id"])
        
    user = await db.users.find_one({"_id": uid})
    if not user:
        logger.warning(f"Recipient user not found: {recipient_id}")
        return None

    # Construct notification document
    doc = create_notification_document(
        user_id=uid,
        title=title,
        message=message,
        type=type,
        link=link,
        actor_id=actor_id,
        actor_name=actor_name,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        course_id=course_id,
        severity=severity,
        email_subject=email_subject,
        metadata=metadata,
    )
    
    result = await db.notifications.insert_one(doc)
    notification_id = str(result.inserted_id)
    doc["_id"] = notification_id
    
    # Determine whether to send email based on user preferences
    user_prefs = user.get("preferences") or {}
    email_enabled = user_prefs.get("email_notifications", True)
    push_enabled = user_prefs.get("push_notifications", False)
    
    if email_enabled and user.get("email"):
        asyncio.create_task(_send_notification_email_async(notification_id, user["email"], doc))
        
    if push_enabled and user.get("push_subscriptions"):
        asyncio.create_task(_send_web_push_async(user["push_subscriptions"], doc))
        
    return notification_id

async def _send_web_push_async(subscriptions: list, notification_data: dict):
    from pywebpush import webpush, WebPushException
    from app.config.settings import settings
    import json
    
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_CLAIM_EMAIL:
        logger.warning("VAPID keys not configured. Cannot send web push.")
        return
        
    payload = json.dumps({
        "title": notification_data.get("title", "EduAI Alert"),
        "body": notification_data.get("message", ""),
        "icon": "/logo.png",
        "url": notification_data.get("link", "/")
    })
    
    def _do_push(sub):
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CLAIM_EMAIL}
            )
        except WebPushException as ex:
            logger.error(f"Web Push failed for endpoint {sub.get('endpoint')}: {repr(ex)}")
        except Exception as e:
            logger.error(f"Unexpected error sending web push: {e}")

    for sub in subscriptions:
        await asyncio.to_thread(_do_push, sub)


async def _send_notification_email_async(notification_id: str, email: str, notification_data: dict):
    """Background worker to deliver HTML email safely without crashing business workflows."""
    db = get_database()
    try:
        success = send_event_notification_email(email, notification_data)
        if success:
            await db.notifications.update_one(
                {"_id": ObjectId(notification_id)},
                {"$set": {"email_sent": True, "email_sent_at": datetime.now(UTC)}}
            )
        else:
            await db.notifications.update_one(
                {"_id": ObjectId(notification_id)},
                {"$set": {"email_sent": False, "email_error": "SMTP Delivery Failed"}}
            )
    except Exception as e:
        logger.error(f"Failed background email delivery for notification {notification_id}: {e}")
        try:
            await db.notifications.update_one(
                {"_id": ObjectId(notification_id)},
                {"$set": {"email_sent": False, "email_error": str(e)}}
            )
        except Exception:
            pass


async def create_notification(user_id: str, title: str, message: str, type: str = "info", link: str = None) -> str:
    """Legacy helper maintained for 100% backward compatibility."""
    res = await dispatch_targeted_notification(
        recipient_id=user_id,
        title=title,
        message=message,
        type=type,
        link=link,
    )
    return res or ""


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

