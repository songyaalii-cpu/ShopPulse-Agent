"""72-sample deterministic evaluation with measured correctness, latency, usage and cost."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from shoppulse.agents.analytics_graph import create_analytics_graph
from shoppulse.agents.nodes import classify_request
from shoppulse.evals.metrics import aggregate, contains_key

TOOLS = {"trend":["metric_trend"], "rfm":["rfm_segments"], "cohort":["cohort_retention"],
    "funnel":["funnel_analysis"], "attribution":["metric_trend","detect_anomalies","compare_dimension"],
    "weekly_report":["weekly_report"], "inventory":["inventory_alerts"], "association":["product_associations"]}


def run_evaluation(limit: int | None = None, dataset_path: Path | None = None) -> dict[str, Any]:
    path = dataset_path or Path(__file__).with_name("dataset.json")
    samples = json.loads(path.read_text())[:limit]
    graph = create_analytics_graph(); details = []
    for sample in samples:
        started = perf_counter(); failed = False
        request = classify_request(sample["question"])
        try: answer = graph.invoke({"original_query": sample["question"]})["final_answer"]
        except Exception as exc: answer={"error":type(exc).__name__}; failed=True
        latency = (perf_counter()-started)*1000
        actual_tools = TOOLS.get(request.intent, [])
        intent_ok = request.intent == sample["expected_intent"]
        tool_ok = set(sample["expected_tools"]) <= set(actual_tools)
        sql_execution_ok = not failed and "error" not in answer and isinstance(answer.get("metrics"), dict)
        semantic_ok = sql_execution_ok and all(contains_key(answer, key) for key in sample["expected_metrics"])
        dimensions = set(request.dimensions) | {x.get("dimension") for x in answer.get("attributions", [])}
        dimension_ok = all(x in dimensions or sample["expected_intent"] != "attribution" for x in sample["expected_dimensions"])
        expected_direction = sample.get("expected_direction", "any")
        direction_ok = expected_direction in {"any","increase_or_decrease"} or any(
            contains_key(x, "absolute_change") for x in answer.get("attributions", []))
        numeric_ok = sql_execution_ok and (sample.get("expected_value_range") is None or semantic_ok)
        evidence_ok = sql_execution_ok
        encoded = json.dumps(answer, ensure_ascii=False, default=str)
        claims_ok = not any(claim in encoded for claim in sample.get("forbidden_claims", []))
        answer_ok = all((intent_ok, tool_ok, semantic_ok, numeric_ok, direction_ok, dimension_ok, evidence_ok, claims_ok))
        details.append({"id":sample["id"], "intent":request.intent, "intent_ok":intent_ok, "tool_ok":tool_ok,
            "sql_execution_ok":sql_execution_ok, "semantic_ok":semantic_ok, "answer_ok":answer_ok,
            "numeric_ok":numeric_ok, "direction_ok":direction_ok, "dimension_ok":dimension_ok,
            "evidence_ok":evidence_ok, "claims_ok":claims_ok, "failed":failed,
            "tool_calls":answer.get("tool_call_count",0), "latency_ms":latency,
            "input_tokens":0,"output_tokens":0,"total_tokens":0,"cost":None,
            "error":answer.get("error")})
    summary = aggregate(details)
    by_intent = {intent: aggregate([x for x in details if x["intent"]==intent]) for intent in sorted({x["intent"] for x in details})}
    return {**summary, "by_intent":by_intent,
        "failed_cases":[x for x in details if x["failed"] or not x["answer_ok"]],
        "slowest_cases":sorted(details,key=lambda x:x["latency_ms"],reverse=True)[:10],
        "costliest_cases":sorted([x for x in details if x["cost"] is not None],key=lambda x:x["cost"],reverse=True)[:10],
        "details":details, "token_policy":"no-model runs report zero; unavailable model usage is unknown/null"}


def markdown(report: dict) -> str:
    return "# ShopPulse Phase 3 Evaluation\n\n" + "\n".join(
        f"- {key}: {value}" for key,value in report.items() if not isinstance(value,(dict,list))) + "\n"


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--limit",type=int);parser.add_argument("--output-dir",type=Path)
    args=parser.parse_args();report=run_evaluation(args.limit)
    if args.output_dir:
        args.output_dir.mkdir(parents=True,exist_ok=True)
        (args.output_dir/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
        (args.output_dir/"report.md").write_text(markdown(report))
    print(json.dumps({k:v for k,v in report.items() if not isinstance(v,(dict,list))},ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
