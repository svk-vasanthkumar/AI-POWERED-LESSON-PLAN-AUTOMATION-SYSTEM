import pytest
import asyncio
from datetime import datetime, UTC
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

import app.database.mongodb as mongodb
from app.services.notification_service import (
    dispatch_targeted_notification,
    resolve_course_recipients,
    resolve_department_hod,
    create_notification,
    get_user_notifications,
    mark_as_read,
    mark_all_as_read,
)
from app.services.email_service import format_change_diff_html, send_event_notification_email


@pytest.fixture
def mock_db(monkeypatch):
    client = AsyncMongoMockClient()
    database = client["test_db"]
    monkeypatch.setattr(mongodb, "database", database)
    return database


@pytest.mark.asyncio
async def test_resolve_course_recipients(mock_db):
    course_oid = ObjectId()
    faculty_oid = ObjectId()
    hod_oid = ObjectId()

    await mock_db.courses.insert_one({
        "_id": course_oid,
        "course_name": "Test Science",
        "assigned_faculty_id": faculty_oid,
        "department": "Computer Science"
    })
    await mock_db.users.insert_one({
        "_id": faculty_oid,
        "full_name": "Dr. Smith",
        "email": "smith@edu.com",
        "role": "faculty",
        "department": "Computer Science"
    })
    await mock_db.users.insert_one({
        "_id": hod_oid,
        "full_name": "HOD Jane",
        "email": "hod@edu.com",
        "role": "hod",
        "department": "Computer Science"
    })

    recipients = await resolve_course_recipients(str(course_oid))
    assert str(faculty_oid) in recipients
    assert str(hod_oid) in recipients


@pytest.mark.asyncio
async def test_dispatch_targeted_notification_deduplication(mock_db):
    course_oid = ObjectId()
    faculty_oid = ObjectId()

    await mock_db.courses.insert_one({
        "_id": course_oid,
        "course_name": "Math 101",
        "assigned_faculty_id": faculty_oid,
    })
    await mock_db.users.insert_one({
        "_id": faculty_oid,
        "full_name": "Prof Math",
        "email": "math@edu.com",
        "role": "faculty",
    })

    created1 = await dispatch_targeted_notification(
        recipient_id=str(faculty_oid),
        actor_id=str(ObjectId()),
        actor_name="HOD Math",
        event_type="LESSON_PLAN_SUBMITTED",
        entity_type="lesson_plan",
        entity_id="lp_123",
        course_id=str(course_oid),
        title="Lesson Plan Submitted",
        message="Lesson plan for unit 1 submitted",
        severity="INFO"
    )

    assert created1 is not None

    created2 = await dispatch_targeted_notification(
        recipient_id=str(faculty_oid),
        actor_id=str(ObjectId()),
        actor_name="HOD Math",
        event_type="LESSON_PLAN_SUBMITTED",
        entity_type="lesson_plan",
        entity_id="lp_123",
        course_id=str(course_oid),
        title="Lesson Plan Submitted",
        message="Lesson plan for unit 1 submitted",
        severity="INFO"
    )

    # Returns same ID because second attempt was deduplicated
    assert created2 == created1
    count = await mock_db.notifications.count_documents({"user_id": faculty_oid})
    assert count == 1


@pytest.mark.asyncio
async def test_email_service_diff_formatting():
    changes = {
        "status": {"old": "DRAFT", "new": "SUBMITTED"},
        "topics_count": {"old": 5, "new": 9}
    }
    html_diff = format_change_diff_html(changes)

    assert "<table" in html_diff
    assert "DRAFT" in html_diff
    assert "SUBMITTED" in html_diff


@pytest.mark.asyncio
async def test_notification_read_workflow(mock_db):
    user_oid = ObjectId()
    await mock_db.users.insert_one({
        "_id": user_oid,
        "full_name": "Test User",
        "email": "test@edu.com",
        "role": "faculty"
    })

    notif_id = await create_notification(
        user_id=str(user_oid),
        title="Test Notification",
        message="Hello World",
        type="info",
        link="/test"
    )

    notifs = await get_user_notifications(str(user_oid))
    assert len(notifs) >= 1
    assert notifs[0]["read"] is False

    await mark_as_read(notif_id, str(user_oid))
    notifs_updated = await get_user_notifications(str(user_oid))
    matched = next((n for n in notifs_updated if n["_id"] == notif_id), None)
    assert matched is not None
    assert matched["read"] is True
