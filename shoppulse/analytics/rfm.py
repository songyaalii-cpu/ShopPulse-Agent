"""Deterministic RFM scoring and named customer segments."""

from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, text

from shoppulse.analytics.periods import data_max_date
from shoppulse.db.session import get_engine


RFM_RULES = {
    "Champions": "R>=4, F>=4, M>=4",
    "Loyal Customers": "F>=4 and M>=3",
    "Potential Loyalists": "R>=4 and F>=2",
    "New Customers": "R=5 and F<=2",
    "At Risk": "R<=2 and F>=3",
    "Hibernating": "R<=2 and F<=2",
    "Lost": "R=1 and F=1",
    "Others": "remaining customers",
}


def rfm_segments(engine: Engine | None = None, sample_size: int = 3) -> dict[str, Any]:
    db = engine or get_engine()
    reference = data_max_date(db) + timedelta(days=1)
    statement = text("""
        WITH refunds AS (
            SELECT customer_id, SUM(refund_amount) AS refunded
            FROM refunds WHERE status='completed' GROUP BY customer_id
        ), base AS (
            SELECT c.id, c.customer_code, c.segment AS customer_segment,
                   (:reference_date - MAX(o.ordered_at)::date) AS recency,
                   COUNT(DISTINCT o.id) AS frequency,
                   SUM(o.paid_amount)-COALESCE(MAX(r.refunded),0) AS monetary,
                   SUM(o.paid_amount)/COUNT(DISTINCT o.id) AS average_order_value
            FROM customers c JOIN orders o ON o.customer_id=c.id AND o.status <> 'cancelled'
            LEFT JOIN refunds r ON r.customer_id=c.id
            GROUP BY c.id, c.customer_code, c.segment
        ), scored AS (
            SELECT *, NTILE(5) OVER (ORDER BY recency DESC, id) AS r_score,
                      NTILE(5) OVER (ORDER BY frequency ASC, id) AS f_score,
                      NTILE(5) OVER (ORDER BY monetary ASC, id) AS m_score
            FROM base
        ), labeled AS (
            SELECT *, CASE
                WHEN r_score>=4 AND f_score>=4 AND m_score>=4 THEN 'Champions'
                WHEN r_score=5 AND f_score<=2 THEN 'New Customers'
                WHEN f_score>=4 AND m_score>=3 THEN 'Loyal Customers'
                WHEN r_score>=4 AND f_score>=2 THEN 'Potential Loyalists'
                WHEN r_score=1 AND f_score=1 THEN 'Lost'
                WHEN r_score<=2 AND f_score>=3 THEN 'At Risk'
                WHEN r_score<=2 AND f_score<=2 THEN 'Hibernating'
                ELSE 'Others' END AS rfm_segment
            FROM scored
        )
        SELECT rfm_segment, COUNT(*) AS customers,
               AVG(recency)::numeric(12,2) AS average_recency,
               AVG(average_order_value)::numeric(14,2) AS average_order_value,
               SUM(monetary)::numeric(16,2) AS net_sales,
               ARRAY_AGG(customer_code ORDER BY monetary DESC) AS customer_samples
        FROM labeled GROUP BY rfm_segment ORDER BY net_sales DESC
    """)
    with db.connect() as connection:
        rows = [dict(row) for row in connection.execute(
            statement, {"reference_date": reference, "sample_size": sample_size}
        ).mappings()]
    total_customers = sum(row["customers"] for row in rows) or 1
    return {
        "reference_date": reference.isoformat(),
        "rules": RFM_RULES,
        "segments": [
            {
                **row,
                "average_recency": float(row["average_recency"]),
                "average_order_value": float(row["average_order_value"]),
                "net_sales": float(row["net_sales"]),
                "customer_share": row["customers"] / total_customers,
                "customer_samples": row["customer_samples"][:sample_size],
            }
            for row in rows
        ],
    }
