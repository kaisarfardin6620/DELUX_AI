import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core import config

MEDIA_ROOT = Path(__file__).resolve().parent.parent / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = config.MEDIA_MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def build_image_url(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return config.FASTAPI_MEDIA_URL.rstrip("/") + "/" + relative_path.lstrip("/")


def _safe_name(filename: str) -> str:
    name = Path(filename).name
    stem = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(name).stem).strip("._-")
    suffix = Path(name).suffix.lower()
    if not stem:
        stem = "file"
    return f"{stem}{suffix}"


def _safe_relative_folder(folder: str) -> Path:
    folder_path = Path(folder)
    if folder_path.is_absolute() or ".." in folder_path.parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid folder path.",
        )
    cleaned_parts = [re.sub(r"[^a-zA-Z0-9._-]", "_", part).strip("._-") for part in folder_path.parts if part not in ("", ".")]
    cleaned_parts = [part for part in cleaned_parts if part]
    if not cleaned_parts:
        return Path("products")
    return Path(*cleaned_parts)


def _validate_upload(upload: UploadFile) -> None:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only jpg, jpeg, png, webp, and gif files are allowed.",
        )

    if upload.content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image content type.",
        )


async def save_uploaded_image(upload: UploadFile, folder: str = "products") -> dict[str, str | int | None]:
    _validate_upload(upload)

    upload_id = uuid.uuid4().hex
    safe_filename = _safe_name(upload.filename or "file")
    relative_directory = _safe_relative_folder(folder)
    destination_directory = MEDIA_ROOT / relative_directory
    destination_directory.mkdir(parents=True, exist_ok=True)

    relative_path = relative_directory / f"{upload_id}_{safe_filename}"
    destination_path = MEDIA_ROOT / relative_path

    total_bytes = 0
    try:
        with destination_path.open("wb") as output_file:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large. Maximum allowed size is {config.MEDIA_MAX_UPLOAD_MB} MB.",
                    )

                output_file.write(chunk)
    except HTTPException:
        if destination_path.exists():
            destination_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return {
        "filename": destination_path.name,
        "relative_path": str(relative_path).replace("\\", "/"),
        "url": build_image_url(str(relative_path).replace("\\", "/")),
        "size_bytes": total_bytes,
    }
