import json

from shoppulse.api.serializers import event_out
from shoppulse.api.services.event_service import append_event
from shoppulse.db.session import db_session
from shoppulse.settings import get_settings


async def emit(redis, run_id: str, event_type: str, payload: dict | None = None, node_name: str | None = None):
    with db_session() as db:
        item = append_event(db, run_id, event_type, payload, node_name)
        data = event_out(item)
    cfg = get_settings(); key = f"{cfg.redis_key_prefix}events:{run_id}"
    encoded = json.dumps(data, ensure_ascii=False, default=str)
    if len(encoded.encode()) > cfg.sse_event_max_bytes:
        data["payload"] = {"summary": "event payload omitted because it exceeded the safe size limit"}
        encoded = json.dumps(data, ensure_ascii=False)
    await redis.xadd(key, {"event": encoded}, maxlen=cfg.sse_stream_max_length, approximate=True)
    await redis.expire(key, cfg.sse_stream_ttl_seconds)
    return data
