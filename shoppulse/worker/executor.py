import asyncio
import hashlib
import json
import socket
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from shoppulse.agents.analytics_graph import create_analytics_graph
from shoppulse.api.errors import safe_message
from shoppulse.db.models import AnalysisRun
from shoppulse.db.session import db_session
from shoppulse.observability.token_usage import TokenUsage
from shoppulse.settings import get_settings
from shoppulse.worker.charts import charts_for
from shoppulse.worker.events import emit


def json_safe(value: Any):
    if isinstance(value, (datetime, date)): return value.isoformat()
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, dict): return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [json_safe(v) for v in value]
    return value


def cache_key(payload: dict) -> str:
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"{get_settings().redis_key_prefix}analysis:v1:{hashlib.sha256(normalized.encode()).hexdigest()}"


async def execute_run(redis, run_id: str) -> dict:
    cfg = get_settings(); started = time.perf_counter()
    with db_session() as db:
        run = db.scalar(select(AnalysisRun).where(AnalysisRun.run_id == run_id).with_for_update())
        if not run: return {"status": "missing"}
        if run.status in {"completed", "failed", "cancelled", "running"}: return {"status": run.status}
        run.status = "running"; run.started_at = datetime.now(UTC); run.worker_id = socket.gethostname()
        run.lease_expires_at = datetime.now(UTC) + timedelta(seconds=cfg.run_lease_seconds)
        payload = run.request_payload
    await emit(redis, run_id, "run.started", {"worker": "arq"})
    key = cache_key(payload)
    cached = await redis.get(key) if cfg.analysis_cache_ttl_seconds else None
    if cached:
        result = json.loads(cached); result["cache_hit"] = True
        await finish_run(redis, run_id, result, started, cache_hit=True)
        return result
    try:
        graph = create_analytics_graph(cfg.workshop_model if payload.get("llm_enabled") and cfg.llm_enabled else None)
        state = {"original_query": payload["query"]}
        iterator = graph.stream(state, stream_mode=["tasks", "updates"])
        final_answer = None; intent = None; tool_calls = 0
        task_started: dict[str, float] = {}
        while True:
            with db_session() as db:
                current = db.scalar(select(AnalysisRun.status).where(AnalysisRun.run_id == run_id))
            if current == "cancelled": return {"status": "cancelled"}
            item = await asyncio.to_thread(next, iterator, None)
            if item is None: break
            mode, data = item
            if mode != "tasks": continue
            task_id, node_name = data["id"], data["name"]
            is_start = "input" in data and "result" not in data and "error" not in data
            if is_start:
                task_started[task_id] = time.perf_counter()
                await emit(redis, run_id, "graph.node.started", {}, node_name)
                if node_name in {"execute_metric", "detect_anomaly", "execute_drilldown"}:
                    await emit(redis, run_id, "tool.started", {"tool": node_name}, node_name)
                continue
            node_update = data.get("result") or {}
            duration_ms = int((time.perf_counter() - task_started.pop(task_id, time.perf_counter())) * 1000)
            summary = {"keys": sorted(node_update), "status": "error" if data.get("error") else "ok",
                "duration_ms": duration_ms}
            if node_name in {"execute_metric", "detect_anomaly", "execute_drilldown"}:
                tool_calls = max(tool_calls, int(node_update.get("tool_call_count", tool_calls)))
                await emit(redis, run_id, "tool.completed", {"tool": node_name,
                    "result_summary": {"keys": summary["keys"]}, "duration_ms": duration_ms}, node_name)
            if node_update.get("intent"): intent = node_update["intent"]
            if node_update.get("final_answer") is not None: final_answer = node_update["final_answer"]
            await emit(redis, run_id, "graph.node.completed", summary, node_name)
            if node_name not in {"write_answer", "handle_error"}:
                await emit(redis, run_id, "analysis.partial", {"completed_node": node_name}, node_name)
        if not final_answer: raise RuntimeError("analytics graph did not produce a final answer")
        result = json_safe({"answer": final_answer, "charts": charts_for(intent or "trend", final_answer),
            "intent": intent, "cache_hit": False})
        for chart in result["charts"]: await emit(redis, run_id, "chart.ready", {"chart": chart})
        if cfg.analysis_cache_ttl_seconds:
            await redis.set(key, json.dumps(result, ensure_ascii=False), ex=cfg.analysis_cache_ttl_seconds)
        await finish_run(redis, run_id, result, started, tool_calls=tool_calls)
        return result
    except Exception as exc:
        message = safe_message(exc)
        with db_session() as db:
            run = db.scalar(select(AnalysisRun).where(AnalysisRun.run_id == run_id).with_for_update())
            if run and run.status != "cancelled":
                run.status = "failed"; run.error_code = "analysis_failed"; run.error_message = message
                run.completed_at = datetime.now(UTC); run.lease_expires_at = None
                run.latency_ms = int((time.perf_counter() - started) * 1000)
        await emit(redis, run_id, "run.failed", {"error_code": "analysis_failed", "message": message})
        return {"status": "failed", "error": message}


async def finish_run(redis, run_id: str, result: dict, started: float, cache_hit: bool = False, tool_calls: int = 0):
    usage = TokenUsage.no_model(); latency = int((time.perf_counter() - started) * 1000)
    with db_session() as db:
        run = db.scalar(select(AnalysisRun).where(AnalysisRun.run_id == run_id).with_for_update())
        if not run or run.status == "cancelled": return
        run.status = "completed"; run.result_payload = result; run.intent = result.get("intent")
        run.completed_at = datetime.now(UTC); run.lease_expires_at = None; run.latency_ms = latency
        run.cache_hit = cache_hit; run.tool_call_count = tool_calls
        run.input_tokens = usage.input_tokens; run.output_tokens = usage.output_tokens
        run.cached_input_tokens = usage.cached_input_tokens; run.reasoning_tokens = usage.reasoning_tokens
        run.total_tokens = usage.total_tokens
    await emit(redis, run_id, "run.completed", {"status": "completed", "latency_ms": latency,
        "cache_hit": cache_hit, "token_usage": usage.to_dict()})
