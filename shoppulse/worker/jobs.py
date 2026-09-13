from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from shoppulse.db.models import AnalysisRun, EvaluationRun
from shoppulse.db.session import db_session
from shoppulse.worker.executor import execute_run


async def execute_analysis_job(ctx, run_id: str):
    return await execute_run(ctx["redis"], run_id)


async def execute_evaluation_job(ctx, evaluation_id: str):
    from shoppulse.evals.runner import run_evaluation
    with db_session() as db:
        item = db.scalar(select(EvaluationRun).where(EvaluationRun.evaluation_id == evaluation_id))
        if not item or item.status != "queued": return
        item.status = "running"; limit = item.sample_limit
    try:
        report = await __import__("asyncio").to_thread(run_evaluation, limit)
        with db_session() as db:
            item = db.scalar(select(EvaluationRun).where(EvaluationRun.evaluation_id == evaluation_id))
            item.status = "completed"; item.report_payload = report; item.completed_at = datetime.now(UTC)
    except Exception as exc:
        with db_session() as db:
            item = db.scalar(select(EvaluationRun).where(EvaluationRun.evaluation_id == evaluation_id))
            item.status = "failed"; item.error_message = str(exc)[:500]; item.completed_at = datetime.now(UTC)


async def recover_stale_runs(ctx):
    now = datetime.now(UTC)
    with db_session() as db:
        stale = list(db.scalars(select(AnalysisRun).where(AnalysisRun.status == "running",
            AnalysisRun.lease_expires_at < now).with_for_update(skip_locked=True)))
        ids = []
        for run in stale:
            run.status = "queued"; run.worker_id = None; run.lease_expires_at = None
            run.retry_count += 1; ids.append(run.run_id)
    for run_id in ids:
        await ctx["redis"].enqueue_job("execute_analysis_job", run_id, _job_id=f"recovery-{run_id}-{int(now.timestamp())}")
    return len(ids)
