from datetime import UTC, datetime
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import get_database
from app.models.faculty_model import create_faculty_document


class FacultyInUseError(Exception):
    """Raised when a faculty member cannot be deleted because records depend on it.

    The API layer maps this to a controlled 409 CONFLICT. Deleting the faculty
    would otherwise orphan the courses, timetables and generated schedules that
    reference it via ``faculty_id``, so restriction is preferred over a
    destructive cascade (the project has no deliberate cascade policy).
    """

    def __init__(self, dependencies: dict[str, int]):
        self.dependencies = dependencies
        summary = ", ".join(f"{count} {name}" for name, count in dependencies.items())
        super().__init__(
            "Faculty cannot be deleted while it is referenced by other records "
            f"({summary}). Remove or reassign them first."
        )


# Collections that hold a ``faculty_id`` reference back to a faculty member.
# Used to protect against orphaning dependent records on delete.
_FACULTY_DEPENDENTS = (
    ("courses", "course(s)"),
    ("timetables", "timetable(s)"),
    ("generated_schedules", "generated schedule(s)"),
)


def _id_variants(value) -> list:
    """Both ObjectId and string forms of an id (legacy-compatible queries)."""
    variants = [value, str(value)]
    if not isinstance(value, ObjectId):
        try:
            variants.append(ObjectId(str(value)))
        except Exception:
            pass
    seen: set = set()
    unique: list = []
    for item in variants:
        key = (type(item).__name__, str(item))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


async def _count_faculty_dependencies(db, faculty_oid) -> dict[str, int]:
    """Count records that reference this faculty, keyed by a friendly name."""
    variants = _id_variants(faculty_oid)
    dependencies: dict[str, int] = {}
    for collection_name, label in _FACULTY_DEPENDENTS:
        count = await db[collection_name].count_documents(
            {"faculty_id": {"$in": variants}}
        )
        if count:
            dependencies[label] = count
    return dependencies


async def create_faculty(data):
    db = get_database()

    existing = await db.faculty.find_one({"faculty_id": data.faculty_id})
    if existing:
        raise ValueError("Faculty ID already exists")

    user = await db.users.find_one(
        {
            "email": data.email.lower(),
            "role": "faculty",
        }
    )

    user_id = None
    if user:
        existing_user_faculty = await db.faculty.find_one({"user_id": user["_id"]})
        if existing_user_faculty:
            raise ValueError("Faculty profile already exists for this user")
        user_id = user["_id"]
    elif getattr(data, "password", None):
        from app.auth.password import hash_password
        from app.models.user_model import create_user_document
        
        user_document = create_user_document(
            name=data.name,
            email=data.email.lower(),
            password=hash_password(data.password),
            role="faculty",
            department=data.department,
        )
        try:
            user_result = await db.users.insert_one(user_document)
            user_id = user_result.inserted_id
        except DuplicateKeyError:
            raise ValueError("User with this email already exists")

    document = create_faculty_document(
        user_id=user_id,
        faculty_id=data.faculty_id,
        name=data.name,
        email=data.email,
        department=data.department,
        designation=data.designation,
    )
    if user_id is None:
        document.pop("user_id", None)

    try:
        result = await db.faculty.insert_one(document)
    except DuplicateKeyError:
        # Unique index on faculty_id raced with the pre-check above; return a
        # controlled 400 instead of an unhandled 500.
        raise ValueError("Faculty ID already exists")

    return str(result.inserted_id)


async def get_all_faculty():
    db = get_database()
    faculty = []

    async for doc in db.faculty.find():
        doc["_id"] = str(doc["_id"])
        doc["has_logged_in"] = False
        if "user_id" in doc:
            doc["user_id"] = str(doc["user_id"])
            user_doc = await db.users.find_one({"_id": ObjectId(doc["user_id"])})
            if user_doc:
                doc["has_logged_in"] = user_doc.get("has_logged_in", False)
        faculty.append(doc)

    return faculty


async def get_faculty(faculty_id: str):
    db = get_database()
    try:
        faculty = await db.faculty.find_one({"_id": ObjectId(faculty_id)})
    except Exception:
        faculty = await db.faculty.find_one({"faculty_id": faculty_id})

    if faculty:
        faculty["_id"] = str(faculty["_id"])
        faculty["has_logged_in"] = False
        if "user_id" in faculty:
            faculty["user_id"] = str(faculty["user_id"])
            user_doc = await db.users.find_one({"_id": ObjectId(faculty["user_id"])})
            if user_doc:
                faculty["has_logged_in"] = user_doc.get("has_logged_in", False)
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
        
    faculty = await db.faculty.find_one({"_id": obj_id})
    if not faculty:
        return 0

    if "faculty_id" in update_data:
        existing = await db.faculty.find_one({"faculty_id": update_data["faculty_id"], "_id": {"$ne": obj_id}})
        if existing:
            raise ValueError("Faculty ID already exists")
            
    if "email" in update_data:
        update_data["email"] = update_data["email"].lower()
        if faculty.get("email") != update_data["email"]:
            existing_user = await db.users.find_one({"email": update_data["email"]})
            if existing_user:
                raise ValueError("Email already in use by another user")
            
            # Update the linked user account if it exists
            if faculty.get("user_id"):
                await db.users.update_one(
                    {"_id": ObjectId(faculty["user_id"])},
                    {"$set": {"email": update_data["email"], "updated_at": datetime.now(UTC)}}
                )

    update_data["updated_at"] = datetime.now(UTC)

    result = await db.faculty.update_one(
        {"_id": obj_id},
        {"$set": update_data},
    )

    return result.modified_count


async def send_welcome_email(faculty_id: str, password: str) -> bool:
    db = get_database()
    try:
        faculty = await db.faculty.find_one({"_id": ObjectId(faculty_id)})
    except Exception:
        faculty = await db.faculty.find_one({"faculty_id": faculty_id})
        
    if not faculty:
        return False
        
    email_address = faculty.get("email")
    name = faculty.get("name")
    
    if "user_id" in faculty:
        from app.auth.password import hash_password
        await db.users.update_one(
            {"_id": faculty["user_id"]},
            {"$set": {"password": hash_password(password)}}
        )
    
    # Use the real email service
    from app.services.email_service import send_email
    from app.config.settings import settings
    frontend_url = settings.frontend_origins_list[0] if settings.frontend_origins_list else "http://localhost:5173"
    login_link = f"{frontend_url}/login"
    
    subject = "Welcome to the EduAI Platform!"
    body_text = (
        f"Dear {name},\n\n"
        f"Your account is created. Please login with your email and the password is the admin given password: {password}\n\n"
        f"For security purposes, you will be required to change this password on your first login.\n\n"
        f"Best regards,\nEduAI System"
    )
    
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #4f46e5;">Welcome to EduAI!</h2>
        <p>Dear {name},</p>
        <p>Your account is created. Please login with your email and the password is the admin given password: <strong>{password}</strong></p>
        <div style="text-align: center; margin: 30px 0;">
          <a href="{login_link}" style="background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Login to your Account</a>
        </div>
        <p style="font-weight: bold; color: #e11d48;">For security purposes, you will be required to change this password on your first login.</p>
        <p>Best regards,<br>EduAI System</p>
      </body>
    </html>
    """
    
    return send_email(email_address, subject, body_text, body_html)


async def delete_faculty(faculty_id: str):
    """Delete a faculty member, refusing to orphan dependent records.

    Raises :class:`FacultyInUseError` (-> 409) when any course, timetable or
    generated schedule still references the faculty. Returns the deleted count
    (0 -> 404) otherwise.
    """
    db = get_database()

    try:
        obj_id = ObjectId(faculty_id)
    except InvalidId:
        return 0

    existing = await db.faculty.find_one({"_id": obj_id})
    if existing is None:
        return 0

    dependencies = await _count_faculty_dependencies(db, obj_id)
    if dependencies:
        raise FacultyInUseError(dependencies)

    result = await db.faculty.delete_one({"_id": obj_id})
    return result.deleted_count