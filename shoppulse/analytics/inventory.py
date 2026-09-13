"""Read-only inventory risk estimates from latest snapshots and recent sales."""

from typing import Any

from sqlalchemy import Engine, text

from shoppulse.db.session import get_engine


def inventory_alerts(engine: Engine | None = None, limit: int = 50) -> list[dict[str, Any]]:
    statement = text("""
        WITH latest_day AS (SELECT MAX(snapshot_date) AS day FROM inventory_snapshots),
        stock AS (
            SELECT i.product_id, SUM(i.available_quantity) AS available,
                   SUM(i.reserved_quantity) AS reserved, SUM(i.inbound_quantity) AS inbound
            FROM inventory_snapshots i JOIN latest_day d ON i.snapshot_date=d.day GROUP BY i.product_id
        ), sales AS (
            SELECT oi.product_id,
                   SUM(oi.quantity) FILTER (WHERE o.ordered_at >= d.day-INTERVAL '7 days')/7.0 AS velocity_7d,
                   SUM(oi.quantity) FILTER (WHERE o.ordered_at >= d.day-INTERVAL '14 days')/14.0 AS velocity_14d,
                   SUM(oi.quantity) FILTER (WHERE o.ordered_at >= d.day-INTERVAL '30 days')/30.0 AS velocity_30d
            FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN latest_day d ON TRUE
            WHERE o.status <> 'cancelled' AND o.ordered_at::date <= d.day
            GROUP BY oi.product_id
        )
        SELECT p.sku,p.name,s.available,s.reserved,s.inbound,
               COALESCE(v.velocity_7d,0) AS velocity_7d, COALESCE(v.velocity_14d,0) AS velocity_14d,
               COALESCE(v.velocity_30d,0) AS velocity_30d,
               CASE WHEN COALESCE(v.velocity_14d,0)=0 THEN NULL ELSE s.available/v.velocity_14d END AS days_of_supply,
               CASE WHEN s.available=0 THEN 'stockout'
                    WHEN COALESCE(v.velocity_14d,0)>0 AND s.available/v.velocity_14d<7 THEN 'low_stock'
                    WHEN COALESCE(v.velocity_30d,0)=0 AND s.available>200 THEN 'overstock'
                    ELSE 'normal' END AS alert
        FROM stock s JOIN products p ON p.id=s.product_id LEFT JOIN sales v ON v.product_id=s.product_id
        WHERE s.available=0 OR (COALESCE(v.velocity_14d,0)>0 AND s.available/v.velocity_14d<7)
           OR (COALESCE(v.velocity_30d,0)=0 AND s.available>200)
        ORDER BY CASE WHEN s.available=0 THEN 0 ELSE 1 END, days_of_supply NULLS LAST LIMIT :limit
    """)
    with (engine or get_engine()).connect() as connection:
        return [{key: float(value) if key.startswith("velocity_") or key == "days_of_supply" else value for key, value in dict(row).items()} for row in connection.execute(statement, {"limit": limit}).mappings()]
