import json
from pathlib import Path

from fastapi.testclient import TestClient

from shoppulse.api.app import create_app
from shoppulse.api.errors import safe_message
from shoppulse.api.schemas import RunCreate
from shoppulse.evals.metrics import aggregate, percentile
from shoppulse.observability.token_usage import TokenUsage, estimate_cost
from shoppulse.worker.executor import cache_key


class DummyRedis:
    async def ping(self): return True


def test_liveness_and_request_id():
    with TestClient(create_app(DummyRedis())) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_development_cors_accepts_remapped_local_frontend_port(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    from shoppulse.settings import get_settings
    get_settings.cache_clear()
    try:
        with TestClient(create_app(DummyRedis())) as client:
            response = client.options(
                "/api/v1/sessions",
                headers={
                    "Origin": "http://localhost:13000",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,x-client-id",
                },
            )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:13000"
    finally:
        get_settings.cache_clear()


def test_query_validation_and_error_redaction():
    assert RunCreate(query="分析 GMV").llm_enabled is False
    redacted = safe_message("postgresql://user:password@host/db api_key=secret")
    assert "password" not in redacted and "secret" not in redacted


def test_cache_key_is_order_independent_and_namespaced():
    assert cache_key({"a": 1, "b": 2}) == cache_key({"b": 2, "a": 1})
    assert cache_key({"a": 1}).startswith("shoppulse:analysis:v1:")


def test_percentiles_use_measured_interpolation():
    assert percentile([1, 2, 3, 4], .5) == 2.5
    assert percentile([], .95) == 0


def test_token_unknown_zero_and_unknown_model_cost(tmp_path):
    assert TokenUsage().total_tokens is None
    assert TokenUsage.no_model().total_tokens == 0
    pricing = tmp_path / "pricing.json"
    pricing.write_text(json.dumps({"models": {}}))
    assert estimate_cost(TokenUsage(10, 2, total_tokens=12, model="unknown"), pricing) is None


def test_metric_formulas_and_failure_collection():
    row = {"intent_ok": True, "tool_ok": True, "sql_execution_ok": True, "semantic_ok": True,
        "answer_ok": True, "numeric_ok": True, "direction_ok": True, "dimension_ok": True,
        "evidence_ok": True, "claims_ok": True, "failed": False, "tool_calls": 2,
        "latency_ms": 10, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost": None}
    report = aggregate([row, {**row, "sql_execution_ok": False, "answer_ok": False, "failed": True, "latency_ms": 20}])
    assert report["sql_execution_accuracy"] == .5
    assert report["answer_correctness"] == .5
    assert report["failure_rate"] == .5
    assert report["p50_latency_ms"] == 15


def test_phase3_dataset_has_required_72_samples():
    samples = json.loads(Path("shoppulse/evals/dataset.json").read_text())
    required = {"id","question","expected_intent","expected_tools","expected_metrics","expected_dimensions",
        "expected_direction","reference_sql","expected_value_range","required_evidence","forbidden_claims","tags"}
    assert len(samples) == 72
    assert all(required <= set(sample) for sample in samples)
