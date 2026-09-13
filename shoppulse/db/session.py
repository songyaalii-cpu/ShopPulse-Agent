"""Synchronous SQLAlchemy 2.0 engine, sessions, and transactions."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from shoppulse.settings import Settings, get_settings


@lru_cache
def _engine_for_url(
    url: str, pool_size: int, max_overflow: int, pool_timeout: int
) -> Engine:
    options: dict = {"pool_pre_ping": True, "future": True}
    if not url.startswith("sqlite"):
        options.update(
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
        )
    return create_engine(url, **options)


def get_engine(settings: Settings | None = None) -> Engine:
    cfg = settings or get_settings()
    return _engine_for_url(
        cfg.database_url,
        cfg.db_pool_size,
        cfg.db_max_overflow,
        cfg.db_pool_timeout_seconds,
    )


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(settings), expire_on_commit=False, class_=Session)


@contextmanager
def db_session(settings: Settings | None = None) -> Iterator[Session]:
    """Commit a unit of work, rolling it back on every exception."""
    session = get_session_factory(settings)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def health_check(settings: Settings | None = None) -> bool:
    with get_engine(settings).connect() as connection:
        return connection.scalar(text("SELECT 1")) == 1
