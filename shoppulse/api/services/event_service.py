from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoppulse.db.models import AnalysisRunEvent


def append_event(db: Session, run_id: str, event_type: str, payload: dict | None = None,
                 node_name: str | None = None) -> AnalysisRunEvent:
    sequence = (db.scalar(select(func.coalesce(func.max(AnalysisRunEvent.sequence), 0)).where(
        AnalysisRunEvent.run_id == run_id)) or 0) + 1
    event = AnalysisRunEvent(event_id=str(uuid4()), run_id=run_id, sequence=sequence,
        event_type=event_type, node_name=node_name, payload=payload or {})
    db.add(event); db.flush(); return event


def events_after(db: Session, run_id: str, sequence: int = 0):
    return list(db.scalars(select(AnalysisRunEvent).where(AnalysisRunEvent.run_id == run_id,
        AnalysisRunEvent.sequence > sequence).order_by(AnalysisRunEvent.sequence)))
