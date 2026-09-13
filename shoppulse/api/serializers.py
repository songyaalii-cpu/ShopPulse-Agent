from decimal import Decimal

from shoppulse.db.models import AgentSession, AnalysisRun, AnalysisRunEvent, EvaluationRun


def session_out(item: AgentSession) -> dict:
    return {"session_id": item.session_id, "title": item.title, "created_at": item.created_at,
        "updated_at": item.updated_at, "last_activity_at": item.last_activity_at, "metadata": item.metadata_json}


def run_out(item: AnalysisRun) -> dict:
    return {"run_id": item.run_id, "session_id": item.session_id, "status": item.status,
        "query": item.query, "intent": item.intent, "result": item.result_payload,
        "error_code": item.error_code, "error_message": item.error_message,
        "events_url": f"/api/v1/runs/{item.run_id}/events", "latency_ms": item.latency_ms,
        "token_usage": {"input_tokens": item.input_tokens, "output_tokens": item.output_tokens,
            "cached_input_tokens": item.cached_input_tokens, "reasoning_tokens": item.reasoning_tokens,
            "total_tokens": item.total_tokens, "model": item.model_name, "provider": item.model_provider},
        "estimated_cost": float(item.estimated_cost) if isinstance(item.estimated_cost, Decimal) else item.estimated_cost,
        "created_at": item.created_at, "started_at": item.started_at, "completed_at": item.completed_at}


def event_out(item: AnalysisRunEvent) -> dict:
    return {"event_id": item.event_id, "run_id": item.run_id, "sequence": item.sequence,
        "event_type": item.event_type, "timestamp": item.created_at.isoformat(),
        "node_name": item.node_name, "payload": item.payload}


def evaluation_out(item: EvaluationRun) -> dict:
    return {"evaluation_id": item.evaluation_id, "status": item.status, "dataset_name": item.dataset_name,
        "sample_limit": item.sample_limit, "report": item.report_payload, "error_message": item.error_message,
        "created_at": item.created_at, "completed_at": item.completed_at}
