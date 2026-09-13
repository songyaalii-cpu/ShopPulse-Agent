"""Product-pair association metrics from valid orders."""

from typing import Any

from sqlalchemy import Engine, text

from shoppulse.db.session import get_engine


def product_associations(
    engine: Engine | None = None, min_support: float = 0.0001, limit: int = 20
) -> list[dict[str, Any]]:
    if not 0 < min_support < 1 or not 1 <= limit <= 100:
        raise ValueError("invalid association thresholds")
    statement = text("""
        WITH valid AS (
            SELECT oi.order_id, oi.product_id FROM order_items oi JOIN orders o ON o.id=oi.order_id
            WHERE o.status <> 'cancelled'
        ), totals AS (SELECT COUNT(DISTINCT order_id)::numeric AS orders FROM valid),
        product_counts AS (SELECT product_id, COUNT(DISTINCT order_id)::numeric AS orders FROM valid GROUP BY product_id),
        pairs AS (
            SELECT a.product_id AS left_id, b.product_id AS right_id, COUNT(DISTINCT a.order_id)::numeric AS pair_orders
            FROM valid a JOIN valid b ON a.order_id=b.order_id AND a.product_id<b.product_id
            GROUP BY a.product_id,b.product_id
        )
        SELECT lp.sku AS left_sku, rp.sku AS right_sku, pairs.pair_orders::int AS pair_orders,
               pairs.pair_orders/totals.orders AS support,
               pairs.pair_orders/lc.orders AS confidence,
               (pairs.pair_orders/lc.orders)/(rc.orders/totals.orders) AS lift
        FROM pairs JOIN totals ON TRUE JOIN product_counts lc ON lc.product_id=pairs.left_id
        JOIN product_counts rc ON rc.product_id=pairs.right_id
        JOIN products lp ON lp.id=pairs.left_id JOIN products rp ON rp.id=pairs.right_id
        WHERE pairs.pair_orders/totals.orders >= :min_support
        ORDER BY lift DESC, pair_orders DESC LIMIT :limit
    """)
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(statement, {"min_support": min_support, "limit": limit}).mappings()
        return [{key: float(value) if key in {"support", "confidence", "lift"} else value for key, value in dict(row).items()} for row in rows]
