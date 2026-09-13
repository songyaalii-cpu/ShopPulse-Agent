"""Parameterized database tools backed by the ShopPulse SQLAlchemy layer."""

from decimal import Decimal
from functools import lru_cache
from typing import Any

from langchain.tools import tool
from langchain_community.utilities import SQLDatabase
from sqlalchemy import text

from shoppulse.db.session import get_engine
from shoppulse.db.sql_safety import UnsafeSQLError, execute_read_only
from shoppulse.settings import get_settings


@lru_cache
def get_database() -> SQLDatabase:
    """Return schema introspection adapter over the shared business engine."""
    return SQLDatabase(get_engine(), include_tables=[
        "customers", "products", "orders", "order_items", "refunds",
        "inventory_snapshots", "marketing_campaigns", "user_events",
    ])


def query_rows(statement: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Run application-owned parameterized SQL through one connection boundary."""
    with get_engine().connect() as connection:
        return [dict(row) for row in connection.execute(text(statement), parameters).mappings()]


def find_customer_by_email(email: str) -> dict[str, Any] | None:
    rows = query_rows(
        "SELECT customer_code, name FROM customers WHERE email = :email",
        {"email": email},
    )
    return rows[0] if rows else None


def _money(value: Any) -> str:
    return f"{Decimal(str(value)):.2f}"


@tool
def get_order_status(order_id: str) -> str:
    """Get status and timestamps for an order number."""
    rows = query_rows(
        """SELECT order_no, ordered_at, status, shipped_at, completed_at
           FROM orders WHERE order_no = :order_no""",
        {"order_no": order_id},
    )
    if not rows:
        return f"Order {order_id} not found."
    row = rows[0]
    response = f"Order {row['order_no']}:\n- Status: {row['status']}\n- Order Date: {row['ordered_at']}\n"
    if row["shipped_at"]:
        response += f"- Shipped Date: {row['shipped_at']}\n"
    if row["completed_at"]:
        response += f"- Completed Date: {row['completed_at']}\n"
    return response


@tool
def get_order_items(order_id: str) -> str:
    """Get product SKUs and quantities for an order number."""
    rows = query_rows(
        """SELECT p.sku, oi.quantity FROM order_items oi
           JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id
           WHERE o.order_no=:order_no ORDER BY oi.id""",
        {"order_no": order_id},
    )
    if not rows:
        return f"No items found for order {order_id}."
    return f"Items in order {order_id}:\n" + "".join(
        f"- Product ID: {row['sku']}, Quantity: {row['quantity']}\n" for row in rows
    )


@tool
def get_product_info(product_identifier: str) -> str:
    """Get product details by exact SKU, otherwise by a safely bound name fragment."""
    rows = query_rows(
        """SELECT sku,name,category,sale_price,status FROM products
           WHERE sku=:identifier OR name ILIKE :pattern
           ORDER BY CASE WHEN sku=:identifier THEN 0 ELSE 1 END LIMIT 1""",
        {"identifier": product_identifier, "pattern": f"%{product_identifier}%"},
    )
    if not rows:
        return f"Product '{product_identifier}' not found."
    row = rows[0]
    stock_status = "In Stock" if row["status"] == "active" else "Out of Stock"
    return f"{row['name']} ({row['sku']})\n- Category: {row['category']}\n- Price: ${_money(row['sale_price'])}\n- Status: {stock_status}"


@tool
def get_order_item_price(order_id: str, product_id: str) -> str:
    """Get historical unit price for a SKU in an order."""
    rows = query_rows(
        """SELECT oi.unit_price,oi.quantity FROM order_items oi
           JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id
           WHERE o.order_no=:order_no AND p.sku=:sku""",
        {"order_no": order_id, "sku": product_id},
    )
    if not rows:
        return f"Item {product_id} not found in order {order_id}."
    row = rows[0]
    return f"Historical price for {product_id} in {order_id}: ${_money(row['unit_price'])} per unit (quantity: {row['quantity']})"


@tool
def get_customer_orders(customer_id: str) -> str:
    """Get recent orders for a customer code."""
    rows = query_rows(
        """SELECT o.order_no,o.ordered_at,o.status FROM orders o
           JOIN customers c ON c.id=o.customer_id
           WHERE c.customer_code=:customer_code ORDER BY o.ordered_at DESC LIMIT 20""",
        {"customer_code": customer_id},
    )
    if not rows:
        return f"No orders found for customer {customer_id}."
    return "Recent orders:\n" + "".join(
        f"- {row['order_no']}: {row['ordered_at']}, {row['status']}\n" for row in rows
    )


@tool
def execute_sql(query: str) -> str:
    """Execute one read-only PostgreSQL SELECT with timeout and row cap."""
    settings = get_settings()
    try:
        with get_engine().connect() as connection:
            result = execute_read_only(
                connection,
                query,
                max_rows=settings.sql_max_rows,
                timeout_ms=settings.sql_query_timeout_ms,
            )
        suffix = f"\n[truncated at {result.max_rows} rows]" if result.truncated else ""
        return f"{result.rows}{suffix}"
    except UnsafeSQLError as exc:
        return f"SQL rejected: {exc}"
    except Exception as exc:
        return f"SQL Error: {exc}"
