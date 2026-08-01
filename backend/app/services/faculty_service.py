from datetime import datetime, UTC
from bson import ObjectId
from bson.errors import InvalidId

from app.database.mongodb import get_database
from app.models.faculty_model import create_faculty_document


async def create_faculty(data):
    db = get_database()

    existing = await db.faculty.find_one({"faculty_id": data.faculty_id})
    if existing:
        raise ValueError("Faculty ID already exists")

    document = create_faculty_document(
        faculty_id=data.faculty_id,
        name=data.name,
        email=data.email,
        department=data.department,
        designation=data.designation,
    )

    result = await db.faculty.insert_one(document)
    return str(result.inserted_id)


async def get_all_faculty():
    db = get_database()
    faculty = []

    async for doc in db.faculty.find():
        doc["_id"] = str(doc["_id"])
        faculty.append(doc)

    return faculty


async def get_faculty(faculty_id: str):
    db = get_database()

    try:
        obj_id = ObjectId(faculty_id)
    except InvalidId:
        return None

    faculty = await db.faculty.find_one({"_id": obj_id})
    if faculty:
        faculty["_id"] = str(faculty["_id"])

    return faculty


async def update_faculty(faculty_id: str, data):
    db = get_database()

    try:
        obj_id = ObjectId(faculty_id)
    except InvalidId:
        return 0

    # Build $set payload dynamically for non-null/provided fields
    update_data = {
        k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None
    }

    if not update_data:
        return 0

    update_data["updated_at"] = datetime.now(UTC)

    result = await db.faculty.update_one(
        {"_id": obj_id},
        {"$set": update_data},
    )

    return result.modified_count


async def delete_faculty(faculty_id: str):
    db = get_database()

    try:
        obj_id = ObjectId(faculty_id)
    except InvalidId:
        return 0

    result = await db.faculty.delete_one({"_id": obj_id})
    return result.deleted_count