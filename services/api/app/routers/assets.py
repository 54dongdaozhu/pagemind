from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.database import User
from app.services import db_log
from app.services.asset_service import get_image_asset, save_image_asset
from app.services.auth_service import get_current_user


router = APIRouter(prefix="/api/assets", tags=["assets"])


class ImageAssetUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str | None = Field(default=None, max_length=128)
    data_base64: str = Field(..., min_length=1)
    relative_path: str | None = Field(default=None, max_length=1024)


@router.post("/images")
def upload_image_asset(
    request: ImageAssetUploadRequest,
    current_user: User = Depends(get_current_user),
):
    result = save_image_asset(
        user_id=current_user.user_id,
        filename=request.filename,
        content_type=request.content_type,
        data_base64=request.data_base64,
        relative_path=request.relative_path,
    )
    db_log.log_event(
        entity_type="asset",
        entity_id=result["asset_id"],
        event_type="asset.image_uploaded",
        user_id=current_user.user_id,
        after_state={
            "filename": request.filename,
            "relative_path": request.relative_path,
            "content_type": result["content_type"],
            "size": result["size"],
        },
    )
    return result


@router.get("/images/{asset_id}")
def get_image(asset_id: str):
    asset_path, content_type = get_image_asset(asset_id)
    return FileResponse(asset_path, media_type=content_type)
