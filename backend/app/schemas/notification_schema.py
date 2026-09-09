from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

class NotificationResponse(BaseModel):
    id: str = Field(alias="_id")
    user_id: str
    recipient_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: Optional[str] = "System"
    title: str
    message: str
    type: str = "info"
    event_type: Optional[str] = "GENERAL"
    entity_type: Optional[str] = "GENERAL"
    entity_id: Optional[str] = None
    course_id: Optional[str] = None
    severity: Optional[str] = "INFO"
    link: Optional[str] = None
    read: bool = False
    email_sent: Optional[bool] = False
    email_sent_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = {}
    created_at: datetime
    
    class Config:
        populate_by_name = True

class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str

class PushSubscriptionSchema(BaseModel):
    endpoint: str
    expirationTime: Optional[Any] = None
    keys: PushSubscriptionKeys
