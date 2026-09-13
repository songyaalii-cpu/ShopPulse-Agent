from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from shoppulse.api.dependencies import get_db, owner_id
from shoppulse.api.errors import APIError
from shoppulse.api.schemas import Page, SessionCreate, SessionOut
from shoppulse.api.serializers import session_out
from shoppulse.api.services import session_service

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=201)
def create(body: SessionCreate, db: Session = Depends(get_db), owner: str = Depends(owner_id)):
    return session_out(session_service.create_session(db, body.title, owner, body.metadata))


@router.get("", response_model=Page)
def listing(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), owner: str = Depends(owner_id)):
    items, total = session_service.list_sessions(db, owner, page, page_size)
    return {"items": [session_out(x) for x in items], "page": page, "page_size": page_size, "total": total}


@router.get("/{session_id}", response_model=SessionOut)
def detail(session_id: str, db: Session = Depends(get_db), owner: str = Depends(owner_id)):
    item = session_service.get_session(db, session_id, owner)
    if not item: raise APIError(404, "session_not_found", "会话不存在")
    return session_out(item)


@router.delete("/{session_id}", status_code=204)
def delete(session_id: str, db: Session = Depends(get_db), owner: str = Depends(owner_id)):
    item = session_service.get_session(db, session_id, owner)
    if not item: raise APIError(404, "session_not_found", "会话不存在")
    db.delete(item)
