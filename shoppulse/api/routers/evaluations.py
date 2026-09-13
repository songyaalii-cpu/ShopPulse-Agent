from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoppulse.api.dependencies import get_db
from shoppulse.api.errors import APIError
from shoppulse.api.schemas import EvaluationCreate, EvaluationOut
from shoppulse.api.serializers import evaluation_out
from shoppulse.db.models import EvaluationRun

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


@router.post("", response_model=EvaluationOut, status_code=202)
async def create(body: EvaluationCreate, request: Request, db: Session = Depends(get_db)):
    item = EvaluationRun(evaluation_id=str(uuid4()), dataset_name=body.dataset_name, sample_limit=body.sample_limit)
    db.add(item); db.flush(); db.commit()
    try: await request.app.state.redis.enqueue_job("execute_evaluation_job", item.evaluation_id, _job_id=item.evaluation_id)
    except Exception as exc: raise APIError(503, "queue_unavailable", "评测已保存，但队列暂时不可用", True) from exc
    return evaluation_out(item)


@router.get("/{evaluation_id}", response_model=EvaluationOut)
def detail(evaluation_id: str, db: Session = Depends(get_db)):
    item = db.scalar(select(EvaluationRun).where(EvaluationRun.evaluation_id == evaluation_id))
    if not item: raise APIError(404, "evaluation_not_found", "评测不存在")
    return evaluation_out(item)
