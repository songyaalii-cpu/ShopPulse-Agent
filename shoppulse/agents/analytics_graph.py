"""Explicit LangGraph workflow with bounded anomaly-attribution loops."""

from langgraph.graph import END, START, StateGraph

from shoppulse.agents.analytics_state import AnalyticsState
from shoppulse.agents.nodes import make_nodes


def create_analytics_graph(model: str | None = None):
    nodes = make_nodes(model)
    builder = StateGraph(AnalyticsState)
    for name in (
        "parse_request", "select_analysis", "build_plan", "execute_metric", "detect_anomaly",
        "choose_drilldown", "execute_drilldown", "validate_evidence", "write_answer", "handle_error",
    ):
        builder.add_node(name, nodes[name])
    builder.add_edge(START, "parse_request")
    builder.add_conditional_edges(
        "parse_request", lambda state: "error" if state.get("error") else "continue",
        {"error": "handle_error", "continue": "select_analysis"},
    )
    builder.add_edge("select_analysis", "build_plan")
    builder.add_edge("build_plan", "execute_metric")
    builder.add_conditional_edges(
        "execute_metric",
        lambda state: "error" if state.get("error") else "attribute" if state.get("intent") == "attribution" else "answer",
        {"error": "handle_error", "attribute": "detect_anomaly", "answer": "write_answer"},
    )
    builder.add_edge("detect_anomaly", "choose_drilldown")
    builder.add_conditional_edges(
        "choose_drilldown", lambda state: "continue" if state.get("next_dimension") else "validate",
        {"continue": "execute_drilldown", "validate": "validate_evidence"},
    )
    builder.add_edge("execute_drilldown", "choose_drilldown")
    builder.add_edge("validate_evidence", "write_answer")
    builder.add_edge("write_answer", END)
    builder.add_edge("handle_error", END)
    return builder.compile()
