from typing import Any


def charts_for(intent: str, answer: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = answer.get("metrics", {}) or {}; rows = metrics.get("rows", []) if isinstance(metrics, dict) else []
    if intent in {"trend", "attribution"}:
        trend = answer.get("trend", []) or rows
        chart = {"chart_id": "kpi-trend", "chart_type": "line", "title": "核心经营指标趋势",
            "x_axis": [str(x.get("bucket") or x.get("period")) for x in trend], "series": [
                {"name": name, "unit": unit, "data": [x.get(name) for x in trend]}
                for name, unit in (("gmv", "currency"), ("order_count", "count"),
                    ("average_order_value", "currency"), ("refund_rate", "percent"))],
            "metadata": {"currency": "CNY", "source": "metric_trend"}}
        charts = [chart]
        if intent == "attribution":
            levels = answer.get("attributions", [])
            charts.append({"chart_id": "attribution", "chart_type": "bar", "title": "异常维度贡献",
                "categories": [x.get("dimension") for x in levels],
                "series": [{"name": "贡献", "unit": "number", "data": [
                    (x.get("contributors") or [{}])[0].get("contribution", 0) for x in levels]}],
                "metadata": {"drilldown_depth": len(levels), "source": "attribution"}})
        return charts
    if intent == "rfm":
        return [{"chart_id": "rfm", "chart_type": "bar", "title": "RFM 客户分群",
            "categories": [x.get("segment") for x in rows], "series": [
                {"name": "人数", "unit": "count", "data": [x.get("customers") for x in rows]},
                {"name": "净销售贡献", "unit": "currency", "data": [x.get("net_sales") for x in rows]}],
            "metadata": {"source": "rfm_segments"}}]
    if intent == "cohort":
        return [{"chart_id": "cohort", "chart_type": "heatmap", "title": "Cohort 留存",
            "x_axis": [f"M{i}" for i in range(12)], "rows": rows,
            "metadata": {"null_means": "not_mature", "source": "cohort_retention"}}]
    if intent == "funnel":
        return [{"chart_id": "funnel", "chart_type": "funnel", "title": "用户行为漏斗",
            "series": [{"name": "漏斗", "unit": "count", "data": rows}],
            "metadata": {"source": "funnel_analysis"}}]
    if intent == "inventory":
        return [{"chart_id": "inventory", "chart_type": "table", "title": "库存预警",
            "rows": rows, "metadata": {"source": "inventory_alerts"}}]
    if intent == "association":
        return [{"chart_id": "association", "chart_type": "graph", "title": "商品关联",
            "rows": rows, "metadata": {"source": "product_associations"}}]
    return []
