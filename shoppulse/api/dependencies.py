from collections.abc import Iterator

from fastapi import Header, Query, Request
from sqlalchemy.orm import Session

from shoppulse.db.session import get_session_factory
from shoppulse.settings import get_settings


def get_db() -> Iterator[Session]:
    db = get_session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def owner_id(x_client_id: str | None = Header(default=None), client_id: str | None = Query(default=None)) -> str:
    value = x_client_id or client_id or get_settings().demo_user_id
    return value[:64]


def redis_pool(request: Request):
    return request.app.state.redis
