import asyncio
import json

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoppulse.api.dependencies import get_db, owner_id
from shoppulse.api.errors import APIError
from shoppulse.api.serializers import event_out
from shoppulse.api.services.event_service import events_after
from shoppulse.api.services.run_service import get_run
from shoppulse.db.models import AnalysisRunEvent
from shoppulse.settings import get_settings

router = APIRouter(tags=["events"])


def _frame(event: dict) -> str:
    return f"id: {event['event_id']}\nevent: {event['event_type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.get("/api/v1/runs/{run_id}/events")
async def stream(run_id: str, request: Request, last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
                 db: Session = Depends(get_db), owner: str = Depends(owner_id)):
    run = get_run(db, run_id, owner)
    if not run: raise APIError(404, "run_not_found", "任务不存在")
    sequence = 0
    if last_event_id:
        previous = db.scalar(select(AnalysisRunEvent).where(AnalysisRunEvent.run_id == run_id,
            AnalysisRunEvent.event_id == last_event_id))
        if previous: sequence = previous.sequence
    db.close()
    cfg = get_settings()

    async def generate():
        nonlocal sequence
        redis_position = "$"
        while True:
            from shoppulse.db.session import get_session_factory
            with get_session_factory()() as history_db:
                pending = events_after(history_db, run_id, sequence)
                current = get_run(history_db, run_id, owner)
                status = current.status if current else "failed"
            for item in pending:
                sequence = item.sequence
                yield _frame(event_out(item))
            if status in {"completed", "failed", "cancelled"}:
                break
            try:
                rows = await request.app.state.redis.xread(
                    {f"{cfg.redis_key_prefix}events:{run_id}": redis_position},
                    block=cfg.sse_heartbeat_seconds * 1000, count=20)
                if rows and rows[0][1]: redis_position = rows[0][1][-1][0]
                else:
                    yield f"event: heartbeat\ndata: {json.dumps({'run_id': run_id, 'sequence': sequence})}\n\n"
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
