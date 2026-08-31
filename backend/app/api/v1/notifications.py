from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.auth.dependencies import get_current_user
from app.schemas.notification_schema import NotificationResponse
from app.services.notification_service import (
    get_user_notifications,
    mark_as_read,
    mark_all_as_read,
)

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
    dependencies=[Depends(get_current_user)],
)

@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(limit: int = 50, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    return await get_user_notifications(user_id, limit)

@router.put("/read-all")
async def read_all_notifications(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    count = await mark_all_as_read(user_id)
    return {"message": f"Marked {count} notifications as read"}

@router.put("/{notification_id}/read")
async def read_notification(notification_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    success = await mark_as_read(notification_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    return {"message": "Marked as read"}
