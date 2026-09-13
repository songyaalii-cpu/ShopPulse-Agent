from fastapi import APIRouter, Request
from sqlalchemy import text

from shoppulse.db.session import get_engine

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live(): return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request):
    try:
        with get_engine().connect() as connection: connection.execute(text("SELECT 1"))
        await request.app.state.redis.ping()
    except Exception:
        from shoppulse.api.errors import APIError
        raise APIError(503, "dependency_unavailable", "数据库或 Redis 尚未就绪", True)
    return {"status": "ready", "postgres": "ok", "redis": "ok"}
