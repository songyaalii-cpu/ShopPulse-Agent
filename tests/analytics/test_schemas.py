from shoppulse.agents.nodes import classify_request
from shoppulse.analytics.metrics import METRIC_DEFINITIONS


def test_metric_registry_contains_required_canonical_metrics():
    assert {"gmv", "order_count", "average_order_value", "refund_rate", "payment_conversion_rate"} <= set(METRIC_DEFINITIONS)


def test_deterministic_parser_routes_without_model_key():
    request = classify_request("为什么最近一周退款率上升？")
    assert request.intent == "attribution"
    assert request.metrics == ["refund_rate"]
    assert request.require_attribution
