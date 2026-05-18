from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.database import User
from app.modules.auth.service import get_current_user
from app.modules.profile import service as profile_service


router = APIRouter(prefix="/api/profile", tags=["profile"])


class AnalyzeRequest(BaseModel):
    background_text: str


@router.post("/analyze")
def analyze_profile(request: AnalyzeRequest, current_user: User = Depends(get_current_user)):
    if not request.background_text.strip():
        raise HTTPException(status_code=422, detail="背景信息不能为空")
    return profile_service.analyze_and_save(current_user.user_id, request.background_text.strip())


@router.get("/me")
def get_my_profile(current_user: User = Depends(get_current_user)):
    profile = profile_service.get_profile(current_user.user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到用户画像")
    return profile
