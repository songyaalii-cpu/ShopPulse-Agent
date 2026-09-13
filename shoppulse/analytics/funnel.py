"""Session-deduplicated ordered behavior funnels."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import Engine, text

from shoppulse.analytics.periods import resolve_period
from shoppulse.analytics.schemas import Granularity
from shoppulse.db.session import get_engine


FUNNEL_STAGES = ("view", "click", "add_to_cart", "checkout", "purchase")


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def funnel_analysis(
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = "week",
    filters: dict[str, str] | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db = engine or get_engine()
    period = resolve_period(start, end, granularity, db)
    selected = filters or {}
    allowed = {"channel", "device_type", "region", "campaign", "category"}
    unknown = set(selected) - allowed
    if unknown:
        raise ValueError(f"unsupported funnel filters: {sorted(unknown)}")
    mapping = {
        "channel": "e.channel", "device_type": "e.device_type", "region": "c.region",
        "campaign": "mc.campaign_code", "category": "p.category",
    }
    clauses: list[str] = []
    params: dict[str, Any] = {
        "grain": granularity, "start_at": period.start, "end_at": period.end + timedelta(days=1)
    }
    for key, value in selected.items():
        clauses.append(f"{mapping[key]} = :filter_{key}")
        params[f"filter_{key}"] = value
    where = " AND " + " AND ".join(clauses) if clauses else ""
    statement = text(f"""
        WITH event_first AS (
            SELECT e.session_id, e.event_type, MIN(e.occurred_at) AS first_at
            FROM user_events e LEFT JOIN customers c ON c.id=e.customer_id
            LEFT JOIN products p ON p.id=e.product_id
            LEFT JOIN marketing_campaigns mc ON mc.id=e.campaign_id
            WHERE e.occurred_at >= :start_at AND e.occurred_at < :end_at {where}
            GROUP BY e.session_id, e.event_type
        ), sessions AS (
            SELECT session_id, date_trunc(:grain, MIN(first_at))::date AS bucket,
                   MIN(first_at) FILTER (WHERE event_type='view') AS view_at,
                   MIN(first_at) FILTER (WHERE event_type='click') AS click_at,
                   MIN(first_at) FILTER (WHERE event_type='add_to_cart') AS cart_at,
                   MIN(first_at) FILTER (WHERE event_type='checkout') AS checkout_at,
                   MIN(first_at) FILTER (WHERE event_type='purchase') AS purchase_at
            FROM event_first GROUP BY session_id
        )
        SELECT bucket,
               COUNT(*) FILTER (WHERE view_at IS NOT NULL) AS view_sessions,
               COUNT(*) FILTER (WHERE cart_at >= view_at) AS add_to_cart_sessions,
               COUNT(*) FILTER (WHERE checkout_at >= cart_at AND cart_at >= view_at) AS checkout_sessions,
               COUNT(*) FILTER (WHERE purchase_at >= checkout_at AND checkout_at >= cart_at AND cart_at >= view_at) AS purchase_sessions,
               COUNT(*) FILTER (WHERE (click_at IS NOT NULL AND click_at < view_at)
                                  OR (cart_at IS NOT NULL AND (view_at IS NULL OR cart_at < view_at))
                                  OR (purchase_at IS NOT NULL AND (checkout_at IS NULL OR purchase_at < checkout_at))) AS invalid_sequence_sessions
        FROM sessions GROUP BY bucket ORDER BY bucket
    """)
    with db.connect() as connection:
        rows = [dict(row) for row in connection.execute(statement, params).mappings()]
    result_rows = []
    for row in rows:
        views, carts, checkouts, purchases = (
            row["view_sessions"], row["add_to_cart_sessions"], row["checkout_sessions"], row["purchase_sessions"]
        )
        result_rows.append({
            **row,
            "view_to_cart_rate": _ratio(carts, views),
            "cart_to_purchase_rate": _ratio(purchases, carts),
            "view_to_purchase_rate": _ratio(purchases, views),
            "payment_conversion_rate": _ratio(purchases, views),
            "view_dropoff_rate": 1 - _ratio(carts, views) if views else 0.0,
            "cart_dropoff_rate": 1 - _ratio(purchases, carts) if carts else 0.0,
        })
    totals = {key: sum(row[key] for row in rows) for key in (
        "view_sessions", "add_to_cart_sessions", "checkout_sessions", "purchase_sessions", "invalid_sequence_sessions"
    )}
    totals.update({
        "view_to_cart_rate": _ratio(totals["add_to_cart_sessions"], totals["view_sessions"]),
        "cart_to_purchase_rate": _ratio(totals["purchase_sessions"], totals["add_to_cart_sessions"]),
        "view_to_purchase_rate": _ratio(totals["purchase_sessions"], totals["view_sessions"]),
        "payment_conversion_rate": _ratio(totals["purchase_sessions"], totals["view_sessions"]),
    })
    return {"period": period.model_dump(mode="json"), "filters": selected, "stages": FUNNEL_STAGES, "totals": totals, "trend": result_rows}
