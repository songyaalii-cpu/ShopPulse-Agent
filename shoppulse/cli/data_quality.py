"""Run ShopPulse data-quality checks and print a machine-readable report."""

import argparse
import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from shoppulse.db.session import get_engine

TABLES = (
    "customers", "products", "marketing_campaigns", "orders", "order_items",
    "refunds", "inventory_snapshots", "user_events",
)


def _scalar(connection, sql: str) -> int:
    return int(connection.scalar(text(sql)) or 0)


def run_checks() -> dict[str, Any]:
    with get_engine().connect() as connection:
        counts = {table: _scalar(connection, f"SELECT COUNT(*) FROM {table}") for table in TABLES}
        orphan_foreign_keys = {
            "orders_customer": _scalar(connection, "SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON c.id=o.customer_id WHERE c.id IS NULL"),
            "order_items_order": _scalar(connection, "SELECT COUNT(*) FROM order_items i LEFT JOIN orders o ON o.id=i.order_id WHERE o.id IS NULL"),
            "order_items_product": _scalar(connection, "SELECT COUNT(*) FROM order_items i LEFT JOIN products p ON p.id=i.product_id WHERE p.id IS NULL"),
            "refunds_order": _scalar(connection, "SELECT COUNT(*) FROM refunds r LEFT JOIN orders o ON o.id=r.order_id WHERE o.id IS NULL"),
            "events_customer": _scalar(connection, "SELECT COUNT(*) FROM user_events e LEFT JOIN customers c ON c.id=e.customer_id WHERE e.customer_id IS NOT NULL AND c.id IS NULL"),
        }
        duplicate_business_numbers = {
            "customer_code": _scalar(connection, "SELECT COUNT(*) FROM (SELECT customer_code FROM customers GROUP BY customer_code HAVING COUNT(*)>1) q"),
            "sku": _scalar(connection, "SELECT COUNT(*) FROM (SELECT sku FROM products GROUP BY sku HAVING COUNT(*)>1) q"),
            "order_no": _scalar(connection, "SELECT COUNT(*) FROM (SELECT order_no FROM orders GROUP BY order_no HAVING COUNT(*)>1) q"),
            "refund_no": _scalar(connection, "SELECT COUNT(*) FROM (SELECT refund_no FROM refunds GROUP BY refund_no HAVING COUNT(*)>1) q"),
            "event_id": _scalar(connection, "SELECT COUNT(*) FROM (SELECT event_id FROM user_events GROUP BY event_id HAVING COUNT(*)>1) q"),
        }
        abnormal_nulls = {
            "customer_dimensions": _scalar(connection, "SELECT COUNT(*) FROM customers WHERE customer_code IS NULL OR email IS NULL OR region IS NULL"),
            "product_dimensions": _scalar(connection, "SELECT COUNT(*) FROM products WHERE sku IS NULL OR category IS NULL OR sale_price IS NULL"),
            "order_dimensions": _scalar(connection, "SELECT COUNT(*) FROM orders WHERE order_no IS NULL OR customer_id IS NULL OR ordered_at IS NULL"),
            "event_dimensions": _scalar(connection, "SELECT COUNT(*) FROM user_events WHERE event_id IS NULL OR session_id IS NULL OR occurred_at IS NULL"),
        }
        order_amount_mismatches = _scalar(connection, """
            SELECT COUNT(*) FROM (
              SELECT o.id FROM orders o LEFT JOIN order_items i ON i.order_id=o.id
              GROUP BY o.id,o.status,o.order_amount,o.discount_amount,o.paid_amount,o.shipping_fee
              HAVING ABS(o.order_amount-COALESCE(SUM(i.quantity*i.unit_price),0))>0.01
                 OR ABS(o.discount_amount-COALESCE(SUM(i.discount_amount),0))>0.01
                 OR ABS(o.paid_amount-(o.order_amount-o.discount_amount+o.shipping_fee))>0.01
            ) q
        """)
        excessive_refunds = _scalar(connection, """
            SELECT COUNT(*) FROM (
              SELECT o.id FROM orders o JOIN refunds r ON r.order_id=o.id AND r.status<>'rejected'
              GROUP BY o.id,o.paid_amount HAVING SUM(r.refund_amount)>o.paid_amount
            ) q
        """)
        abnormal_event_sequences = _scalar(connection, """
            SELECT COUNT(*) FROM (
              SELECT session_id,
                MIN(occurred_at) FILTER (WHERE event_type='view') viewed,
                MIN(occurred_at) FILTER (WHERE event_type='click') clicked,
                MIN(occurred_at) FILTER (WHERE event_type='add_to_cart') carted,
                MIN(occurred_at) FILTER (WHERE event_type='checkout') checked_out,
                MIN(occurred_at) FILTER (WHERE event_type='purchase') purchased
              FROM user_events GROUP BY session_id
            ) s WHERE (clicked IS NOT NULL AND (viewed IS NULL OR clicked<viewed))
                       OR (carted IS NOT NULL AND (clicked IS NULL OR carted<clicked))
                       OR (checked_out IS NOT NULL AND (carted IS NULL OR checked_out<carted))
                       OR (purchased IS NOT NULL AND (checked_out IS NULL OR purchased<checked_out))
        """)
        metrics = dict(connection.execute(text("""
            SELECT COALESCE(SUM(order_amount) FILTER (WHERE status<>'cancelled'),0)::numeric(18,2) gmv,
                   COALESCE(SUM(paid_amount) FILTER (WHERE status<>'cancelled'),0)::numeric(18,2) paid_amount,
                   COALESCE(SUM(paid_amount) FILTER (WHERE status<>'cancelled'),0)
                     / NULLIF(COUNT(*) FILTER (WHERE status<>'cancelled'),0) AS average_order_value
            FROM orders
        """)).mappings().one())
        metrics["refund_amount"] = connection.scalar(text("SELECT COALESCE(SUM(refund_amount) FILTER (WHERE status='completed'),0) FROM refunds"))
        metrics["net_sales"] = Decimal(metrics["paid_amount"] or 0) - Decimal(metrics["refund_amount"] or 0)
        metrics["gross_profit"] = connection.scalar(text("SELECT COALESCE(SUM(line_amount-quantity*unit_cost),0) FROM order_items"))

    issue_groups = (orphan_foreign_keys, duplicate_business_numbers, abnormal_nulls)
    passed = all(value == 0 for group in issue_groups for value in group.values()) and order_amount_mismatches == 0 and excessive_refunds == 0 and abnormal_event_sequences == 0
    return {
        "passed": passed, "table_counts": counts, "orphan_foreign_keys": orphan_foreign_keys,
        "duplicate_business_numbers": duplicate_business_numbers, "abnormal_nulls": abnormal_nulls,
        "order_amount_mismatches": order_amount_mismatches, "excessive_refunds": excessive_refunds,
        "abnormal_event_sequences": abnormal_event_sequences,
        "core_metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-fail", action="store_true", help="Always exit zero after printing")
    args = parser.parse_args()
    report = run_checks()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not report["passed"] and not args.no_fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
