from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoppulse.db.models import AnalysisRun, AgentSession


def create_run(db: Session, session: AgentSession, payload: dict, key: str) -> tuple[AnalysisRun, bool]:
    existing = db.scalar(select(AnalysisRun).where(AnalysisRun.session_id == session.session_id,
        AnalysisRun.idempotency_key == key))
    if existing: return existing, False
    run = AnalysisRun(run_id=str(uuid4()), session_id=session.session_id, idempotency_key=key,
        query=payload["query"], request_payload=payload)
    db.add(run); session.last_activity_at = datetime.now(UTC); db.flush(); return run, True


def get_run(db: Session, run_id: str, user_id: str) -> AnalysisRun | None:
    return db.scalar(select(AnalysisRun).join(AgentSession).where(
        AnalysisRun.run_id == run_id, AgentSession.user_id == user_id))


def list_runs(db: Session, session_id: str, page: int, size: int):
    base = select(AnalysisRun).where(AnalysisRun.session_id == session_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    return list(db.scalars(base.order_by(AnalysisRun.created_at.desc()).offset((page-1)*size).limit(size))), total
