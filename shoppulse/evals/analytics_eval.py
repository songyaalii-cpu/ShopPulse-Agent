"""Deterministic local evaluation; no model or LangSmith key is required."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from shoppulse.agents import create_analytics_graph
from shoppulse.agents.nodes import classify_request


TOOL_BY_INTENT = {
    "trend": "metric_trend", "rfm": "rfm_segments", "cohort": "cohort_retention",
    "funnel": "funnel_analysis", "attribution": "compare_dimension", "weekly_report": "weekly_report",
}


def _has_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_has_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_has_key(child, key) for child in value)
    return False


def evaluate(dataset_path: Path, execute: bool = True) -> dict[str, Any]:
    samples = json.loads(dataset_path.read_text())
    graph = create_analytics_graph() if execute else None
    intent_hits = tool_hits = metric_hits = direction_hits = dimension_hits = 0
    metric_total = direction_total = dimension_total = 0
    calls = times = 0.0
    details = []
    for sample in samples:
        started = perf_counter()
        request = classify_request(sample["question"])
        intent_ok = request.intent == sample["expected_intent"]
        tool_ok = TOOL_BY_INTENT[request.intent] == sample["expected_tool"]
        intent_hits += intent_ok
        tool_hits += tool_ok
        answer = graph.invoke({"original_query": sample["question"]})["final_answer"] if graph else {}
        expected_metrics = sample.get("expected_metrics", [])
        if expected_metrics:
            metric_total += 1
            metric_ok = all(metric in request.metrics and (not execute or _has_key(answer, metric)) for metric in expected_metrics)
            metric_hits += metric_ok
        else:
            metric_ok = True
        expected_dimensions = sample.get("expected_dimensions", [])
        if expected_dimensions:
            dimension_total += 1
            actual_dimensions = {row.get("dimension") for row in answer.get("attributions", [])} if execute else set(request.dimensions)
            dimension_ok = set(expected_dimensions) <= (actual_dimensions | set(request.dimensions))
            dimension_hits += dimension_ok
        else:
            dimension_ok = True
        expected_direction = sample.get("expected_direction")
        if expected_direction:
            direction_total += 1
            changes = []
            for level in answer.get("attributions", []):
                if level.get("contributors"):
                    top = level["contributors"][0]
                    changes.extend([top["absolute_change"], top.get("peer_gap", 0)])
            direction_ok = any(change > 0 for change in changes) if expected_direction == "increase" else any(change < 0 for change in changes)
            direction_hits += direction_ok
        else:
            direction_ok = True
        elapsed = perf_counter() - started
        times += elapsed
        calls += answer.get("tool_call_count", 0)
        details.append({"question": sample["question"], "intent": intent_ok, "tool": tool_ok, "metric": metric_ok, "dimension": dimension_ok, "direction": direction_ok, "seconds": elapsed})
    count = len(samples)
    return {
        "samples": count,
        "intent_accuracy": intent_hits / count,
        "tool_selection_accuracy": tool_hits / count,
        "metric_accuracy": metric_hits / metric_total if metric_total else 1.0,
        "anomaly_direction_accuracy": direction_hits / direction_total if direction_total else 1.0,
        "attribution_dimension_hit_rate": dimension_hits / dimension_total if dimension_total else 1.0,
        "average_tool_calls": calls / count if execute else 0,
        "average_execution_seconds": times / count,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("analytics_dataset.json"))
    parser.add_argument("--parse-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset, execute=not args.parse_only), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
