from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.account.auth import verify_token
from app.media_api.services import save_uploaded_image

router = APIRouter(prefix="/api/media", tags=["media"])
security = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> int:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token.")

    try:
        return verify_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    folder: str = Form(default="products"),
    user_id: int = Depends(get_current_user_id),
):
    saved_file = await save_uploaded_image(file, folder=folder)
    return {
        "user_id": user_id,
        **saved_file,
    }
