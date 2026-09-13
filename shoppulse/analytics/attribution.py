"""Whitelisted dimension comparisons and bounded multi-level attribution."""

from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, text

from shoppulse.analytics.schemas import DatePeriod
from shoppulse.db.session import get_engine


ALLOWED_DIMENSIONS = ("region", "channel", "category", "segment", "campaign", "device_type")
SUPPORTED_METRICS = {
    "gmv", "order_count", "paid_amount", "refund_amount", "net_sales",
    "average_order_value", "refund_rate", "gross_profit", "gross_margin",
    "payment_conversion_rate",
}


def _period_dimension_values(
    metric: str,
    dimension: str,
    period: DatePeriod,
    filters: dict[str, str],
    engine: Engine,
) -> list[dict[str, Any]]:
    if dimension not in ALLOWED_DIMENSIONS:
        raise ValueError(f"unsupported dimension: {dimension}")
    if metric not in SUPPORTED_METRICS:
        raise ValueError(f"unsupported attribution metric: {metric}")
    unknown = set(filters) - set(ALLOWED_DIMENSIONS)
    if unknown:
        raise ValueError(f"unsupported attribution filters: {sorted(unknown)}")
    if metric == "payment_conversion_rate":
        return _event_dimension_values(dimension, period, filters, engine)
    dimension_column = {
        "region": "region", "channel": "channel", "category": "category",
        "segment": "segment", "campaign": "campaign", "device_type": "'not_applicable'",
    }[dimension]
    clauses = []
    params: dict[str, Any] = {"start_at": period.start, "end_at": period.end + timedelta(days=1)}
    for key, value in filters.items():
        if key == "device_type":
            continue
        if key == dimension:
            continue
        clauses.append(f"{key} = :filter_{key}")
        params[f"filter_{key}"] = value
    where = " AND " + " AND ".join(clauses) if clauses else ""
    statement = text(f"""
        WITH refund_by_order AS (
            SELECT order_id, SUM(refund_amount) FILTER (WHERE status='completed') AS refund_amount
            FROM refunds GROUP BY order_id
        ), item_by_order AS (
            SELECT oi.order_id,
                   SUM(oi.line_amount-oi.quantity*oi.unit_cost) AS gross_profit,
                   (ARRAY_AGG(p.category ORDER BY oi.line_amount DESC))[1] AS category
            FROM order_items oi JOIN products p ON p.id=oi.product_id GROUP BY oi.order_id
        ), fact AS (
            SELECT o.id, o.region, o.channel, c.segment,
                   COALESCE(mc.campaign_code,'none') AS campaign,
                   COALESCE(i.category,'unknown') AS category,
                   o.order_amount, o.paid_amount, COALESCE(r.refund_amount,0) AS refund_amount,
                   COALESCE(i.gross_profit,0) AS gross_profit
            FROM orders o JOIN customers c ON c.id=o.customer_id
            LEFT JOIN marketing_campaigns mc ON mc.id=o.campaign_id
            LEFT JOIN refund_by_order r ON r.order_id=o.id
            LEFT JOIN item_by_order i ON i.order_id=o.id
            WHERE o.status <> 'cancelled' AND o.ordered_at >= :start_at AND o.ordered_at < :end_at
        ), grouped AS (
            SELECT {dimension_column}::text AS dimension_value,
                   SUM(order_amount) AS gmv, COUNT(DISTINCT id) AS order_count,
                   SUM(paid_amount) AS paid_amount, SUM(refund_amount) AS refund_amount,
                   SUM(gross_profit) AS gross_profit
            FROM fact WHERE TRUE {where} GROUP BY {dimension_column}
        )
        SELECT dimension_value,
               CASE :metric
                 WHEN 'gmv' THEN gmv WHEN 'order_count' THEN order_count
                 WHEN 'paid_amount' THEN paid_amount WHEN 'refund_amount' THEN refund_amount
                 WHEN 'net_sales' THEN paid_amount-refund_amount
                 WHEN 'average_order_value' THEN CASE WHEN order_count=0 THEN 0 ELSE paid_amount/order_count END
                 WHEN 'refund_rate' THEN CASE WHEN paid_amount=0 THEN 0 ELSE refund_amount/paid_amount END
                 WHEN 'gross_profit' THEN gross_profit
                 WHEN 'gross_margin' THEN CASE WHEN gmv=0 THEN 0 ELSE gross_profit/gmv END
               END AS metric_value,
               CASE WHEN :metric IN ('refund_rate') THEN refund_amount ELSE
                    CASE WHEN :metric IN ('average_order_value') THEN paid_amount ELSE NULL END END AS numerator,
               CASE WHEN :metric IN ('refund_rate') THEN paid_amount ELSE
                    CASE WHEN :metric IN ('average_order_value') THEN order_count ELSE NULL END END AS denominator
        FROM grouped ORDER BY ABS(CASE :metric WHEN 'gmv' THEN gmv WHEN 'order_count' THEN order_count
          WHEN 'paid_amount' THEN paid_amount WHEN 'refund_amount' THEN refund_amount
          WHEN 'net_sales' THEN paid_amount-refund_amount WHEN 'average_order_value' THEN paid_amount/NULLIF(order_count,0)
          WHEN 'refund_rate' THEN refund_amount/NULLIF(paid_amount,0) WHEN 'gross_profit' THEN gross_profit
          WHEN 'gross_margin' THEN gross_profit/NULLIF(gmv,0) END) DESC NULLS LAST
    """)
    params["metric"] = metric
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(statement, params).mappings()]


def _event_dimension_values(
    dimension: str, period: DatePeriod, filters: dict[str, str], engine: Engine
) -> list[dict[str, Any]]:
    columns = {
        "region": "COALESCE(c.region,'anonymous')", "channel": "e.channel",
        "category": "COALESCE(p.category,'unknown')", "segment": "COALESCE(c.segment,'anonymous')",
        "campaign": "COALESCE(mc.campaign_code,'none')", "device_type": "e.device_type",
    }
    clauses: list[str] = []
    params: dict[str, Any] = {"start_at": period.start, "end_at": period.end + timedelta(days=1)}
    for key, value in filters.items():
        if key == dimension:
            continue
        clauses.append(f"{columns[key]} = :filter_{key}")
        params[f"filter_{key}"] = value
    where = " AND " + " AND ".join(clauses) if clauses else ""
    dim = columns[dimension]
    statement = text(f"""
        WITH event_first AS (
            SELECT e.session_id, {dim}::text AS dimension_value, e.event_type, MIN(e.occurred_at) AS first_at
            FROM user_events e LEFT JOIN customers c ON c.id=e.customer_id
            LEFT JOIN products p ON p.id=e.product_id LEFT JOIN marketing_campaigns mc ON mc.id=e.campaign_id
            WHERE e.occurred_at>=:start_at AND e.occurred_at<:end_at {where}
            GROUP BY e.session_id, dimension_value, e.event_type
        ), sessions AS (
            SELECT session_id, dimension_value,
                   BOOL_OR(event_type='view') AS viewed, BOOL_OR(event_type='purchase') AS purchased
            FROM event_first GROUP BY session_id, dimension_value
        )
        SELECT dimension_value, COUNT(*) FILTER(WHERE purchased)::numeric/NULLIF(COUNT(*) FILTER(WHERE viewed),0) AS metric_value,
               COUNT(*) FILTER(WHERE purchased) AS numerator, COUNT(*) FILTER(WHERE viewed) AS denominator
        FROM sessions GROUP BY dimension_value ORDER BY denominator DESC
    """)
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(statement, params).mappings()]


def compare_dimension(
    metric: str,
    dimension: str,
    current: DatePeriod,
    comparison: DatePeriod,
    filters: dict[str, str] | None = None,
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    db = engine or get_engine()
    selected = filters or {}
    current_rows = {row["dimension_value"]: row for row in _period_dimension_values(metric, dimension, current, selected, db)}
    comparison_rows = {row["dimension_value"]: row for row in _period_dimension_values(metric, dimension, comparison, selected, db)}
    result = []
    for value in sorted(set(current_rows) | set(comparison_rows)):
        now = current_rows.get(value, {})
        before = comparison_rows.get(value, {})
        current_value = float(now.get("metric_value") or 0)
        previous_value = float(before.get("metric_value") or 0)
        delta = current_value - previous_value
        result.append({
            "dimension": dimension, "value": value,
            "current_value": current_value, "comparison_value": previous_value,
            "absolute_change": delta,
            "relative_change": delta / abs(previous_value) if previous_value else (1.0 if current_value else 0.0),
            "current_numerator": float(now.get("numerator") or 0),
            "current_denominator": float(now.get("denominator") or 0),
            "comparison_numerator": float(before.get("numerator") or 0),
            "comparison_denominator": float(before.get("denominator") or 0),
        })
    total_impact = sum(abs(row["absolute_change"]) for row in result) or 1.0
    for row in result:
        row["impact_share"] = abs(row["absolute_change"]) / total_impact
        peers = [candidate["current_value"] for candidate in result if candidate["value"] != row["value"]]
        row["peer_gap"] = row["current_value"] - (sum(peers) / len(peers) if peers else row["current_value"])
    if dimension in selected:
        result = [row for row in result if row["value"] == selected[dimension]]
    return sorted(result, key=lambda row: abs(row["absolute_change"]), reverse=True)


def multi_dimensional_attribution(
    metric: str,
    current: DatePeriod,
    comparison: DatePeriod,
    dimensions: list[str] | None = None,
    filters: dict[str, str] | None = None,
    max_depth: int = 3,
    top_n: int = 5,
    engine: Engine | None = None,
) -> dict[str, Any]:
    if not 1 <= max_depth <= 3:
        raise ValueError("max_depth must be between 1 and 3")
    planned = dimensions or ["region", "channel", "category", "segment"]
    if len(planned) != len(set(planned)) or set(planned) - set(ALLOWED_DIMENSIONS):
        raise ValueError("dimensions must be unique values from the attribution whitelist")
    selected = dict(filters or {})
    levels: list[dict[str, Any]] = []
    for depth, dimension in enumerate(planned[:max_depth], 1):
        rows = compare_dimension(metric, dimension, current, comparison, selected, engine)
        levels.append({"depth": depth, "dimension": dimension, "filters": dict(selected), "contributors": rows[:top_n]})
        if not rows or rows[0]["impact_share"] < 0.05:
            break
        selected[dimension] = rows[0]["value"]
    return {
        "metric": metric,
        "current_period": current.model_dump(mode="json"),
        "comparison_period": comparison.model_dump(mode="json"),
        "levels": levels,
        "stop_reason": "maximum_depth" if len(levels) == max_depth else "insufficient_marginal_contribution",
        "limitations": ["Dimension attribution describes contribution and association, not proven causality."],
    }
