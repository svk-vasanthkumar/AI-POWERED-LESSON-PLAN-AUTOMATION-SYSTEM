from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status


def to_object_id(value, field: str = "id") -> ObjectId:
    """Safely validate and convert a value to a MongoDB ObjectId.

    - If ``value`` is already an ObjectId it is returned unchanged.
    - If ``value`` is a valid 24-character hex string it is converted.
    - Otherwise a clean HTTP 400 is raised instead of letting an
      ``InvalidId``/``TypeError`` bubble up as an unhandled 500.

    Raising ``HTTPException`` here means callers in either the service or
    API layer get consistent client-error responses for malformed IDs.
    """
    if isinstance(value, ObjectId):
        return value

    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}: '{value}' is not a valid ObjectId",
        )
