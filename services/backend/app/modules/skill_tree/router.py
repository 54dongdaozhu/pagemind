from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.modules.auth.service import get_current_user
from app.modules.skill_tree.service import (
    create_snapshot,
    generate_skill_tree_job,
    get_generating_snapshot,
    get_latest_snapshot,
    get_snapshot_status,
)
from app.shared.job_queue import enqueue_job


router = APIRouter(prefix="/api/skill-tree", tags=["skill_tree"])


class GenerateRequest(BaseModel):
    force: bool = False


@router.get("")
def get_skill_tree(current_user=Depends(get_current_user)):
    result = get_latest_snapshot(current_user.user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="暂无技能树快照，请先生成")
    return result


@router.post("/generate", status_code=202)
def trigger_generate(body: GenerateRequest = GenerateRequest(), current_user=Depends(get_current_user)):
    user_id = current_user.user_id
    if not body.force:
        existing = get_generating_snapshot(user_id)
        if existing:
            return {"snapshot_id": existing, "status": "generating", "message": "已有生成任务进行中"}

    snapshot_id = create_snapshot(user_id, trigger="manual")
    enqueued = enqueue_job(generate_skill_tree_job, user_id, snapshot_id)
    if not enqueued:
        from app.modules.skill_tree.service import _mark_failed
        _mark_failed(snapshot_id, "RQ not available", None)
        raise HTTPException(status_code=503, detail="后台任务队列不可用，请确保 Worker 运行中")

    return {"snapshot_id": snapshot_id, "status": "generating"}


@router.get("/status/{snapshot_id}")
def get_status(snapshot_id: str, current_user=Depends(get_current_user)):
    result = get_snapshot_status(snapshot_id)
    if result is None:
        raise HTTPException(status_code=404, detail="快照不存在")
    return result
