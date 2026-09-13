"""Explicit state schema for the bounded analytics workflow."""

from typing import Any, NotRequired, TypedDict


class AnalyticsState(TypedDict):
    original_query: NotRequired[str]
    messages: NotRequired[list[Any]]
    request: NotRequired[dict[str, Any]]
    intent: NotRequired[str]
    period: NotRequired[dict[str, Any]]
    comparison_period: NotRequired[dict[str, Any]]
    filters: NotRequired[dict[str, str]]
    requested_metrics: NotRequired[list[str]]
    plan: NotRequired[list[str]]
    tool_results: NotRequired[dict[str, Any]]
    trend_results: NotRequired[list[dict[str, Any]]]
    anomaly_results: NotRequired[list[dict[str, Any]]]
    drilldown_history: NotRequired[list[dict[str, Any]]]
    next_dimension: NotRequired[str | None]
    evidence: NotRequired[list[dict[str, Any]]]
    warnings: NotRequired[list[str]]
    retry_count: NotRequired[int]
    tool_call_count: NotRequired[int]
    final_answer: NotRequired[dict[str, Any]]
    error: NotRequired[str | None]
