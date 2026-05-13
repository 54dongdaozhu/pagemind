import base64
import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

from app.core.config import DATA_DIR


ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
}
MAX_IMAGE_BYTES = 12 * 1024 * 1024
ASSET_ID_RE = re.compile(r"^[a-f0-9]{32}$")
IMAGE_ASSET_DIR = DATA_DIR / "assets" / "images"


def save_image_asset(
    *,
    user_id: str,
    filename: str,
    content_type: str | None,
    data_base64: str,
    relative_path: str | None = None,
) -> dict:
    resolved_type = _resolve_content_type(filename, content_type)
    if resolved_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持常见图片格式")

    try:
        image_bytes = base64.b64decode(_strip_data_uri(data_base64), validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片数据不是有效的 base64") from exc

    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片不能为空")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="图片不能超过 12MB")

    asset_id = uuid.uuid4().hex
    extension = ALLOWED_IMAGE_TYPES[resolved_type]
    IMAGE_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    asset_path = IMAGE_ASSET_DIR / f"{asset_id}{extension}"
    meta_path = IMAGE_ASSET_DIR / f"{asset_id}.json"

    asset_path.write_bytes(image_bytes)
    meta_path.write_text(json.dumps({
        "asset_id": asset_id,
        "user_id": user_id,
        "filename": filename,
        "relative_path": relative_path or "",
        "content_type": resolved_type,
        "size": len(image_bytes),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False), encoding="utf-8")

    return {
        "asset_id": asset_id,
        "url": f"/api/assets/images/{asset_id}",
        "content_type": resolved_type,
        "size": len(image_bytes),
    }


def get_image_asset(asset_id: str) -> tuple[Path, str]:
    if not ASSET_ID_RE.match(asset_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")

    for content_type, extension in ALLOWED_IMAGE_TYPES.items():
        asset_path = IMAGE_ASSET_DIR / f"{asset_id}{extension}"
        if asset_path.is_file():
            return asset_path, content_type

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")


def _strip_data_uri(data: str) -> str:
    value = str(data or "").strip()
    if "," in value and value.lower().startswith("data:"):
        return value.split(",", 1)[1]
    return value


def _resolve_content_type(filename: str, content_type: str | None) -> str:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type in ALLOWED_IMAGE_TYPES:
        return normalized_type

    guessed_type, _encoding = mimetypes.guess_type(filename or "")
    if guessed_type in ALLOWED_IMAGE_TYPES:
        return guessed_type
    return normalized_type
