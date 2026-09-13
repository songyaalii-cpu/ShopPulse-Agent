from uuid import uuid4
import time

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from shoppulse.api.dependencies import get_db, owner_id
from shoppulse.api.errors import APIError
from shoppulse.api.schemas import Page, RunCreate, RunSummary
from shoppulse.api.serializers import run_out
from shoppulse.api.services import run_service, session_service
from shoppulse.api.services.event_service import append_event
from shoppulse.settings import get_settings

router = APIRouter(tags=["runs"])


@router.post("/api/v1/sessions/{session_id}/runs", response_model=RunSummary, status_code=202)
async def submit(session_id: str, body: RunCreate, request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db), owner: str = Depends(owner_id)):
    cfg = get_settings()
    if len(body.filters) > cfg.max_filters: raise APIError(422, "too_many_filters", "过滤条件过多")
    rate_key = f"{cfg.redis_key_prefix}rate:submit:{owner}:{int(time.time() // 60)}"
    try:
        attempts = await request.app.state.redis.incr(rate_key)
        if attempts == 1: await request.app.state.redis.expire(rate_key, 70)
    except Exception as exc:
        raise APIError(503, "queue_unavailable", "Redis 暂时不可用，请稍后重试", True) from exc
    if attempts > cfg.submit_rate_limit_per_minute:
        raise APIError(429, "rate_limited", "提交过于频繁，请稍后重试", True)
    session = session_service.get_session(db, session_id, owner)
    if not session: raise APIError(404, "session_not_found", "会话不存在")
    key = (idempotency_key or str(uuid4()))[:128]
    run, created = run_service.create_run(db, session, body.model_dump(mode="json"), key)
    if created:
        append_event(db, run.run_id, "run.queued", {"status": "queued"})
        db.commit()
        try:
            await request.app.state.redis.enqueue_job("execute_analysis_job", run.run_id, _job_id=run.run_id)
        except Exception as exc:
            raise APIError(503, "queue_unavailable", "任务已保存，但队列暂时不可用，请用相同幂等键重试", True) from exc
    return run_out(run)


@router.get("/api/v1/runs/{run_id}", response_model=RunSummary)
def detail(run_id: str, db: Session = Depends(get_db), owner: str = Depends(owner_id)):
    item = run_service.get_run(db, run_id, owner)
    if not item: raise APIError(404, "run_not_found", "任务不存在")
    return run_out(item)


@router.post("/api/v1/runs/{run_id}/cancel", response_model=RunSummary)
def cancel(run_id: str, db: Session = Depends(get_db), owner: str = Depends(owner_id)):
    item = run_service.get_run(db, run_id, owner)
    if not item: raise APIError(404, "run_not_found", "任务不存在")
    if item.status in {"completed", "failed", "cancelled"}: raise APIError(409, "run_terminal", "任务已结束")
    item.status = "cancelled"; append_event(db, run_id, "run.cancelled", {"status": "cancelled"})
    return run_out(item)


@router.get("/api/v1/sessions/{session_id}/runs", response_model=Page)
def listing(session_id: str, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db), owner: str = Depends(owner_id)):
    if not session_service.get_session(db, session_id, owner): raise APIError(404, "session_not_found", "会话不存在")
    items, total = run_service.list_runs(db, session_id, page, page_size)
    return {"items": [run_out(x) for x in items], "page": page, "page_size": page_size, "total": total}
