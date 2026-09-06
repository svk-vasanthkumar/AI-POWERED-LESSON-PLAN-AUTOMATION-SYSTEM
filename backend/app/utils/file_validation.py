import os
from fastapi import HTTPException, UploadFile, status
from app.config.settings import settings

_CHUNK_SIZE = 1024 * 1024  # 1 MB

def validate_extension(filename: str | None, allowed_types: dict[str, str]) -> str:
    """Return the validated lowercase extension (incl. dot) or raise 415."""
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="A file with a valid name is required.",
        )

    # Only consider the base name so inputs like "../../etc/passwd" or
    # "..\\evil.pdf" can never influence the stored path.
    base_name = os.path.basename(filename.replace("\\", "/"))
    _, ext = os.path.splitext(base_name)
    ext = ext.lower()

    if ext not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_types.keys())}",
        )

    return ext

def validate_content_type(ext: str, content_type: str | None, allowed_types: dict[str, str]) -> None:
    """Reject uploads whose declared MIME type doesn't match the extension."""
    expected = allowed_types[ext]
    provided = (content_type or "").split(";")[0].strip().lower()

    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content type does not match the file extension.",
        )

async def read_within_limit(file: UploadFile) -> bytes:
    """Read the upload, enforcing the configured maximum size (413)."""
    max_bytes = settings.max_upload_size_bytes
    data = bytearray()

    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
            )

    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    return bytes(data)
