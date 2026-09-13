from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoppulse.db.models import AgentSession


def create_session(db: Session, title: str, user_id: str, metadata: dict) -> AgentSession:
    item = AgentSession(session_id=str(uuid4()), title=title, user_id=user_id, metadata_json=metadata)
    db.add(item); db.flush(); return item


def get_session(db: Session, session_id: str, user_id: str) -> AgentSession | None:
    return db.scalar(select(AgentSession).where(AgentSession.session_id == session_id, AgentSession.user_id == user_id))


def list_sessions(db: Session, user_id: str, page: int, size: int):
    base = select(AgentSession).where(AgentSession.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = list(db.scalars(base.order_by(AgentSession.last_activity_at.desc()).offset((page-1)*size).limit(size)))
    return items, total


def touch(item: AgentSession) -> None:
    item.last_activity_at = datetime.now(UTC)
