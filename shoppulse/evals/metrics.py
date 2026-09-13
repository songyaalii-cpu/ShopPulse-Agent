from math import floor
from typing import Any


def rate(hits: int, total: int) -> float:
    return hits / total if total else 1.0


def percentile(values: list[float], p: float) -> float:
    if not values: return 0.0
    ordered = sorted(values); position = (len(ordered) - 1) * p
    low = floor(position); high = min(low + 1, len(ordered) - 1); fraction = position - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict): return key in value or any(contains_key(v, key) for v in value.values())
    if isinstance(value, list): return any(contains_key(v, key) for v in value)
    return False


def aggregate(details: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(details); latencies = [x["latency_ms"] for x in details]
    known_costs = [x["cost"] for x in details if x["cost"] is not None]
    def accuracy(field): return rate(sum(bool(x[field]) for x in details), count)
    return {"sample_count": count, "intent_accuracy": accuracy("intent_ok"),
        "tool_accuracy": accuracy("tool_ok"), "sql_execution_accuracy": accuracy("sql_execution_ok"),
        "semantic_accuracy": accuracy("semantic_ok"), "answer_correctness": accuracy("answer_ok"),
        "numeric_accuracy": accuracy("numeric_ok"), "direction_accuracy": accuracy("direction_ok"),
        "attribution_hit_rate": accuracy("dimension_ok"), "evidence_completeness": accuracy("evidence_ok"),
        "unsupported_claim_rate": 1-accuracy("claims_ok"),
        "average_tool_calls": sum(x["tool_calls"] for x in details)/count if count else 0,
        "average_latency_ms": sum(latencies)/count if count else 0, "p50_latency_ms": percentile(latencies,.5),
        "p95_latency_ms": percentile(latencies,.95),
        "average_input_tokens": sum(x["input_tokens"] or 0 for x in details)/count if count else 0,
        "average_output_tokens": sum(x["output_tokens"] or 0 for x in details)/count if count else 0,
        "average_total_tokens": sum(x["total_tokens"] or 0 for x in details)/count if count else 0,
        "average_cost": sum(known_costs)/len(known_costs) if known_costs else None,
        "total_cost": sum(known_costs) if len(known_costs)==count and count else None,
        "failure_rate": accuracy("failed")}
