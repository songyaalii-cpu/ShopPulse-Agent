"""Canonical KPI registry and PostgreSQL trend queries."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, text

from shoppulse.analytics.periods import resolve_period
from shoppulse.analytics.schemas import DatePeriod, Granularity
from shoppulse.db.session import get_engine


METRIC_DEFINITIONS = {
    "gmv": "Non-cancelled order_amount",
    "order_count": "Distinct non-cancelled orders",
    "paid_amount": "Non-cancelled paid_amount",
    "refund_amount": "Completed refund_amount by refund completion date",
    "net_sales": "paid_amount minus completed refund_amount",
    "average_order_value": "paid_amount divided by non-cancelled orders",
    "gross_profit": "line_amount minus quantity times unit_cost",
    "gross_margin": "gross_profit divided by line_amount",
    "refund_rate": "completed refund_amount divided by paid_amount",
    "payment_conversion_rate": "purchase sessions divided by view sessions",
}

ALLOWED_FILTERS = {"region", "channel", "segment", "category", "campaign", "device_type"}


def _filter_fragments(filters: dict[str, str], scope: str) -> tuple[str, dict[str, str]]:
    unknown = set(filters) - ALLOWED_FILTERS
    if unknown:
        raise ValueError(f"unsupported filters: {sorted(unknown)}")
    params: dict[str, str] = {}
    clauses: list[str] = []
    mapping = {
        "orders": {
            "region": "o.region",
            "channel": "o.channel",
            "segment": "c.segment",
            "campaign": "mc.campaign_code",
        },
        "events": {
            "region": "c.region",
            "channel": "e.channel",
            "segment": "c.segment",
            "category": "p.category",
            "campaign": "mc.campaign_code",
            "device_type": "e.device_type",
        },
    }
    for key, value in filters.items():
        if key == "category" and scope == "orders":
            clauses.append(
                "EXISTS (SELECT 1 FROM order_items foi JOIN products fp ON fp.id=foi.product_id "
                "WHERE foi.order_id=o.id AND fp.category=:filter_category)"
            )
        elif key == "device_type" and scope == "orders":
            continue
        else:
            column = mapping[scope].get(key)
            if not column:
                continue
            clauses.append(f"{column} = :filter_{key}")
        params[f"filter_{key}"] = value
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def _as_number(value: Any) -> float | int:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return value


def metric_trend(
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = "week",
    filters: dict[str, str] | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db = engine or get_engine()
    period = resolve_period(start, end, granularity, db)
    selected_filters = filters or {}
    order_filter, order_params = _filter_fragments(selected_filters, "orders")
    event_filter, event_params = _filter_fragments(selected_filters, "events")
    sql = text(f"""
        WITH order_base AS (
            SELECT o.id, date_trunc(:grain, o.ordered_at)::date AS bucket,
                   o.order_amount, o.paid_amount
            FROM orders o
            JOIN customers c ON c.id=o.customer_id
            LEFT JOIN marketing_campaigns mc ON mc.id=o.campaign_id
            WHERE o.status <> 'cancelled'
              AND o.ordered_at >= :start_at AND o.ordered_at < :end_at
              {order_filter}
        ), order_agg AS (
            SELECT bucket, SUM(order_amount) AS gmv, COUNT(DISTINCT id) AS order_count,
                   SUM(paid_amount) AS paid_amount
            FROM order_base GROUP BY bucket
        ), profit_agg AS (
            SELECT date_trunc(:grain, o.ordered_at)::date AS bucket,
                   SUM(oi.line_amount - oi.quantity * oi.unit_cost) AS gross_profit,
                   SUM(oi.line_amount) AS gross_revenue
            FROM orders o JOIN customers c ON c.id=o.customer_id
            LEFT JOIN marketing_campaigns mc ON mc.id=o.campaign_id
            JOIN order_items oi ON oi.order_id=o.id
            WHERE o.status <> 'cancelled'
              AND o.ordered_at >= :start_at AND o.ordered_at < :end_at
              {order_filter}
            GROUP BY bucket
        ), refund_agg AS (
            SELECT date_trunc(:grain, r.completed_at)::date AS bucket,
                   SUM(r.refund_amount) AS refund_amount
            FROM refunds r JOIN orders o ON o.id=r.order_id
            JOIN customers c ON c.id=o.customer_id
            LEFT JOIN marketing_campaigns mc ON mc.id=o.campaign_id
            WHERE r.status='completed' AND r.completed_at >= :start_at AND r.completed_at < :end_at
              {order_filter}
            GROUP BY bucket
        ), session_stages AS (
            SELECT date_trunc(:grain, MIN(e.occurred_at))::date AS bucket, e.session_id,
                   BOOL_OR(e.event_type='view') AS viewed,
                   BOOL_OR(e.event_type='purchase') AS purchased
            FROM user_events e
            LEFT JOIN customers c ON c.id=e.customer_id
            LEFT JOIN products p ON p.id=e.product_id
            LEFT JOIN marketing_campaigns mc ON mc.id=e.campaign_id
            WHERE e.occurred_at >= :start_at AND e.occurred_at < :end_at
              {event_filter}
            GROUP BY e.session_id
        ), event_agg AS (
            SELECT bucket, COUNT(*) FILTER (WHERE viewed) AS view_sessions,
                   COUNT(*) FILTER (WHERE purchased) AS purchase_sessions
            FROM session_stages GROUP BY bucket
        ), buckets AS (
            SELECT bucket FROM order_agg UNION SELECT bucket FROM refund_agg
            UNION SELECT bucket FROM event_agg
        )
        SELECT b.bucket,
               COALESCE(o.gmv,0) AS gmv, COALESCE(o.order_count,0) AS order_count,
               COALESCE(o.paid_amount,0) AS paid_amount,
               COALESCE(r.refund_amount,0) AS refund_amount,
               COALESCE(o.paid_amount,0)-COALESCE(r.refund_amount,0) AS net_sales,
               CASE WHEN COALESCE(o.order_count,0)=0 THEN 0 ELSE o.paid_amount/o.order_count END AS average_order_value,
               COALESCE(p.gross_profit,0) AS gross_profit,
               CASE WHEN COALESCE(p.gross_revenue,0)=0 THEN 0 ELSE p.gross_profit/p.gross_revenue END AS gross_margin,
               CASE WHEN COALESCE(o.paid_amount,0)=0 THEN 0 ELSE COALESCE(r.refund_amount,0)/o.paid_amount END AS refund_rate,
               CASE WHEN COALESCE(e.view_sessions,0)=0 THEN 0 ELSE e.purchase_sessions::numeric/e.view_sessions END AS payment_conversion_rate
        FROM buckets b LEFT JOIN order_agg o USING(bucket) LEFT JOIN refund_agg r USING(bucket)
        LEFT JOIN profit_agg p USING(bucket) LEFT JOIN event_agg e USING(bucket)
        ORDER BY b.bucket
    """)
    params: dict[str, Any] = {
        "grain": granularity,
        "start_at": period.start,
        "end_at": period.end + timedelta(days=1),
        **order_params,
        **event_params,
    }
    with db.connect() as connection:
        rows = [dict(row) for row in connection.execute(sql, params).mappings()]
    return {
        "period": period.model_dump(mode="json"),
        "filters": selected_filters,
        "definitions": METRIC_DEFINITIONS,
        "rows": [{key: _as_number(value) for key, value in row.items()} for row in rows],
    }
