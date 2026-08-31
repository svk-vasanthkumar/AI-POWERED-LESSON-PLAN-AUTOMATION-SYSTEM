from pydantic import BaseModel, Field
from datetime import datetime

class NotificationResponse(BaseModel):
    id: str = Field(alias="_id")
    user_id: str
    title: str
    message: str
    type: str
    read: bool
    created_at: datetime
    
    class Config:
        populate_by_name = True
