"""Nodes for the explicit ShopPulse analytics StateGraph."""

from datetime import timedelta
import json
from typing import Any

from langchain.chat_models import init_chat_model

from shoppulse.agents.analytics_state import AnalyticsState
from shoppulse.agents.prompts import ANSWER_WRITER_PROMPT, REQUEST_PARSER_PROMPT
from shoppulse.analytics.anomaly import detect_anomalies
from shoppulse.analytics.attribution import ALLOWED_DIMENSIONS, compare_dimension
from shoppulse.analytics.cohort import cohort_retention
from shoppulse.analytics.funnel import funnel_analysis
from shoppulse.analytics.inventory import inventory_alerts
from shoppulse.analytics.association import product_associations
from shoppulse.analytics.metrics import METRIC_DEFINITIONS, metric_trend
from shoppulse.analytics.periods import previous_period, resolve_period
from shoppulse.analytics.rfm import rfm_segments
from shoppulse.analytics.schemas import AnalysisRequest, DatePeriod, NarrativeOutput
from shoppulse.analytics.weekly_report import weekly_report


def classify_request(query: str) -> AnalysisRequest:
    lowered = query.lower()
    if "库存" in query or "缺货" in query or "inventory" in lowered:
        intent = "inventory"
    elif "关联" in query or "搭配" in query or "一起购买" in query or "association" in lowered:
        intent = "association"
    elif "周报" in query or "weekly report" in lowered:
        intent = "weekly_report"
    elif "rfm" in lowered or "分群" in query:
        intent = "rfm"
    elif "cohort" in lowered or "留存" in query:
        intent = "cohort"
    elif "漏斗" in query or "转化" in query and "为什么" not in query:
        intent = "funnel"
    elif "为什么" in query or "归因" in query or "原因" in query or "异常" in query:
        intent = "attribution"
    else:
        intent = "trend"
    metric_map = {
        "退款率": "refund_rate", "客单价": "average_order_value", "订单量": "order_count",
        "订单数": "order_count", "支付转化": "payment_conversion_rate", "转化率": "payment_conversion_rate",
        "毛利率": "gross_margin", "毛利": "gross_profit", "净销售": "net_sales", "gmv": "gmv",
    }
    metrics = [value for key, value in metric_map.items() if key in lowered]
    if not metrics:
        metrics = ["payment_conversion_rate"] if intent == "funnel" else ["gmv", "order_count", "average_order_value"]
    dimensions = [dimension for dimension in ALLOWED_DIMENSIONS if dimension in lowered]
    chinese_dimensions = {"地区": "region", "渠道": "channel", "品类": "category", "用户类型": "segment", "活动": "campaign", "设备": "device_type"}
    dimensions.extend(value for key, value in chinese_dimensions.items() if key in query)
    filters = {}
    if "social" in lowered:
        filters["channel"] = "social"
    if "南区" in query or "south" in lowered:
        filters["region"] = "South"
    return AnalysisRequest(
        original_query=query, intent=intent, metrics=list(dict.fromkeys(metrics)), filters=filters,
        dimensions=list(dict.fromkeys(dimensions)),
        detect_anomalies=intent == "attribution", require_attribution=intent == "attribution",
        generate_report=intent == "weekly_report",
    )


def make_nodes(model: str | None = None):
    parser_model = None
    writer_model = None
    if model:
        # OpenAI-compatible providers such as DeepSeek support tool/function
        # calling but may reject OpenAI's native response_format=json_schema.
        # Pin the portable method instead of relying on the provider default.
        model_options = ({"extra_body": {"thinking": {"type": "disabled"}}}
            if "deepseek" in model.lower() else {})
        chat_model = init_chat_model(model, **model_options)
        parser_model = chat_model.with_structured_output(AnalysisRequest, method="function_calling")
        writer_model = chat_model.with_structured_output(NarrativeOutput, method="function_calling")

    def parse_request(state: AnalyticsState) -> dict[str, Any]:
        query = state.get("original_query") or ""
        if not query and state.get("messages"):
            last = state["messages"][-1]
            query = last.content if hasattr(last, "content") else str(last.get("content", ""))
        if not query:
            return {"error": "ValueError: original_query or messages is required", "request": classify_request("").model_dump(mode="json"), "warnings": []}
        try:
            request = parser_model.invoke([
                {"role": "system", "content": REQUEST_PARSER_PROMPT},
                {"role": "user", "content": query},
            ]) if parser_model else classify_request(query)
        except Exception as exc:
            request = classify_request(query)
            return {"request": request.model_dump(mode="json"), "warnings": [f"model parser unavailable; deterministic fallback used: {type(exc).__name__}"]}
        return {"request": request.model_dump(mode="json"), "warnings": []}

    def select_analysis(state: AnalyticsState) -> dict[str, Any]:
        request = AnalysisRequest.model_validate(state["request"])
        return {"intent": request.intent, "filters": request.filters, "requested_metrics": request.metrics}

    def build_plan(state: AnalyticsState) -> dict[str, Any]:
        request = AnalysisRequest.model_validate(state["request"])
        period = resolve_period(request.start_date, request.end_date, request.granularity)
        if not request.start_date:
            lowered = request.original_query.lower()
            days = 7 if any(token in lowered for token in ("最近一周", "本周", "last week")) else 45 if "45天" in lowered else 60 if "60天" in lowered else None
            if days:
                period = DatePeriod(start=period.end - timedelta(days=days - 1), end=period.end, granularity=request.granularity)
        comparison = previous_period(period)
        dimensions = request.dimensions or ["region", "channel", "category"]
        return {
            "period": period.model_dump(mode="json"), "comparison_period": comparison.model_dump(mode="json"),
            "plan": dimensions[:3], "drilldown_history": [], "tool_call_count": 0, "retry_count": 0,
        }

    def execute_metric(state: AnalyticsState) -> dict[str, Any]:
        try:
            period = DatePeriod.model_validate(state["period"])
            intent = state["intent"]
            if intent in {"trend", "attribution"}:
                result = metric_trend(period.start, period.end, period.granularity, state.get("filters"))
                return {"tool_results": result, "trend_results": result["rows"], "tool_call_count": state["tool_call_count"] + 1, "error": None}
            if intent == "rfm":
                result = rfm_segments()
            elif intent == "cohort":
                result = cohort_retention(filters=state.get("filters"))
            elif intent == "funnel":
                result = funnel_analysis(period.start, period.end, period.granularity, state.get("filters"))
            elif intent == "inventory":
                result = {"rows": inventory_alerts()}
            elif intent == "association":
                result = {"rows": product_associations()}
            else:
                result = weekly_report()
            return {"tool_results": result, "tool_call_count": state["tool_call_count"] + 1, "error": None}
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}", "retry_count": state.get("retry_count", 0) + 1}

    def detect_anomaly(state: AnalyticsState) -> dict[str, Any]:
        metric = state.get("requested_metrics", ["gmv"])[0]
        period = DatePeriod.model_validate(state["period"])
        history_start = period.end - timedelta(weeks=13) + timedelta(days=1)
        history = metric_trend(history_start, period.end, "week", state.get("filters"))["rows"]
        anomalies = detect_anomalies(history, metric) if metric in METRIC_DEFINITIONS else []
        return {"trend_results": history, "anomaly_results": anomalies, "tool_call_count": state["tool_call_count"] + 1}

    def choose_drilldown(state: AnalyticsState) -> dict[str, Any]:
        history = state.get("drilldown_history", [])
        plan = state.get("plan", [])
        if len(history) >= min(3, len(plan)) or state.get("tool_call_count", 0) >= 8:
            return {"next_dimension": None}
        return {"next_dimension": plan[len(history)]}

    def execute_drilldown(state: AnalyticsState) -> dict[str, Any]:
        dimension = state.get("next_dimension")
        if not dimension:
            return {}
        metric = state.get("requested_metrics", ["gmv"])[0]
        current = DatePeriod.model_validate(state["period"])
        comparison = DatePeriod.model_validate(state["comparison_period"])
        history = list(state.get("drilldown_history", []))
        drill_filters = dict(state.get("filters", {}))
        for previous in history:
            contributors = previous.get("contributors", [])
            if contributors:
                drill_filters[previous["dimension"]] = contributors[0]["value"]
        contributors = compare_dimension(metric, dimension, current, comparison, drill_filters)[:5]
        history.append({"depth": len(history) + 1, "dimension": dimension, "filters": drill_filters, "contributors": contributors})
        return {"drilldown_history": history, "tool_call_count": state["tool_call_count"] + 1}

    def validate_evidence(state: AnalyticsState) -> dict[str, Any]:
        evidence = []
        for level in state.get("drilldown_history", []):
            if level["contributors"]:
                evidence.append({"type": "dimension_contribution", "dimension": level["dimension"], "top": level["contributors"][0]})
        warnings = list(state.get("warnings", []))
        if not evidence:
            warnings.append("No dimension exceeded the evidence threshold; returning the available trend only.")
        return {"evidence": evidence, "warnings": warnings}

    def write_answer(state: AnalyticsState) -> dict[str, Any]:
        facts = state.get("tool_results", {})
        evidence = state.get("evidence", [])
        intent = state.get("intent", "trend")
        if intent == "weekly_report":
            summary = facts.get("markdown", "Weekly report unavailable")
        elif intent == "attribution":
            summary = "已完成总体趋势、异常检测和有限多维下钻；贡献关系不代表已证明的因果关系。"
        else:
            summary = f"已完成 {intent} 确定性分析，所有数值来自 PostgreSQL 查询。"
        answer = {
            "summary": summary, "period": state.get("period"), "metrics": facts,
            "trend": state.get("trend_results", []), "anomalies": state.get("anomaly_results", []),
            "attributions": state.get("drilldown_history", []), "evidence": evidence,
            "recommendations": ["优先复核影响份额最高的维度，并用业务日志或实验验证原因。"] if evidence else [],
            "limitations": ["维度贡献表示相关性，不构成因果证明。"],
            "tool_call_count": state.get("tool_call_count", 0), "warnings": state.get("warnings", []),
        }
        if writer_model:
            try:
                narrative = writer_model.invoke([
                    {"role": "system", "content": ANSWER_WRITER_PROMPT},
                    {"role": "user", "content": json.dumps(answer, ensure_ascii=False, default=str)},
                ])
                answer.update(narrative.model_dump())
            except Exception as exc:
                answer["warnings"] = [*answer["warnings"], f"model writer unavailable; deterministic fallback used: {type(exc).__name__}"]
        return {"final_answer": answer}

    def handle_error(state: AnalyticsState) -> dict[str, Any]:
        return {"final_answer": {"summary": "分析执行失败", "error": state.get("error"), "limitations": ["No unsupported fallback values were generated."]}}

    return locals()
