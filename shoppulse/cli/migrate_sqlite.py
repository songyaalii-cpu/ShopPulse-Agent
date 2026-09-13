"""Idempotently import the retained TechHub SQLite reference data into PostgreSQL."""

import argparse
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, func, select
from sqlalchemy.dialects.postgresql import insert

from shoppulse.db.models import Customer, Order, OrderItem, Product
from shoppulse.db.session import get_engine
from shoppulse.settings import get_settings

CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    """Explicitly convert SQLite floats via their decimal string representation."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def read_source(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        raise FileNotFoundError(f"SQLite source not found: {path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"SQLite foreign-key violations: {violations[:5]}")
        data = {
            table: [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("customers", "products", "orders", "order_items")
        }
    finally:
        connection.close()
    validate_source(data)
    return data


def validate_source(data: dict[str, list[dict[str, Any]]]) -> None:
    for table, key in (("customers", "customer_id"), ("products", "product_id"), ("orders", "order_id")):
        values = [row[key] for row in data[table]]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {key} in SQLite {table}")
        if any(value is None for value in values):
            raise ValueError(f"Null {key} in SQLite {table}")
    totals: dict[str, Decimal] = {}
    for item in data["order_items"]:
        totals[item["order_id"]] = totals.get(item["order_id"], Decimal(0)) + money(item["price_per_unit"]) * item["quantity"]
    mismatches = [
        order["order_id"] for order in data["orders"]
        if money(order["total_amount"]) != totals.get(order["order_id"], Decimal(0)).quantize(CENT)
    ]
    if mismatches:
        raise ValueError(f"SQLite order amount mismatches: {mismatches[:10]}")


def _upsert(connection: Connection, model: type, rows: Iterable[dict], key: str) -> None:
    rows = list(rows)
    if not rows:
        return
    statement = insert(model).values(rows)
    updates = {column.name: getattr(statement.excluded, column.name) for column in model.__table__.columns if column.name not in {"id", key, "created_at"}}
    connection.execute(statement.on_conflict_do_update(index_elements=[key], set_=updates))


def migrate(data: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("SQLite migration target must be PostgreSQL")
    with engine.begin() as connection:
        customers = []
        for index, row in enumerate(data["customers"], 1):
            registered = datetime(2023, 1, 1, tzinfo=UTC) + timedelta(days=index)
            customers.append({
                "id": index, "customer_code": row["customer_id"], "name": row["name"],
                "email": row["email"], "phone": row["phone"], "gender": "unknown",
                "birth_date": None, "segment": row["segment"], "region": "North America",
                "province": row["state"], "city": row["city"], "registration_channel": "legacy",
                "registered_at": registered,
            })
        _upsert(connection, Customer, customers, "customer_code")
        customer_ids = dict(connection.execute(select(Customer.customer_code, Customer.id)).all())

        products = []
        for index, row in enumerate(data["products"], 1):
            price = money(row["price"])
            products.append({
                "id": index, "sku": row["product_id"], "name": row["name"],
                "category": row["category"], "subcategory": row["category"], "brand": "TechHub",
                "list_price": price, "sale_price": price, "unit_cost": (price * Decimal("0.65")).quantize(CENT),
                "status": "active" if row["in_stock"] else "inactive",
                "launched_at": datetime(2023, 1, 1, tzinfo=UTC),
            })
        _upsert(connection, Product, products, "sku")
        product_ids = dict(connection.execute(select(Product.sku, Product.id)).all())

        orders = []
        for index, row in enumerate(data["orders"], 1):
            ordered = utc_datetime(row["order_date"])
            status_map = {"Processing": "pending", "Shipped": "shipped", "Delivered": "completed", "Cancelled": "cancelled"}
            paid = money(row["total_amount"])
            shipped = utc_datetime(row["shipped_date"]) if row["shipped_date"] else None
            orders.append({
                "id": index, "order_no": row["order_id"], "customer_id": customer_ids[row["customer_id"]],
                "campaign_id": None, "channel": "legacy", "status": status_map[row["status"]],
                "region": "North America", "order_amount": paid, "discount_amount": Decimal(0),
                "shipping_fee": Decimal(0), "paid_amount": paid, "ordered_at": ordered,
                "paid_at": ordered if row["status"] != "Cancelled" else None, "shipped_at": shipped,
                "completed_at": shipped + timedelta(days=3) if row["status"] == "Delivered" and shipped else None,
            })
        _upsert(connection, Order, orders, "order_no")
        order_ids = dict(connection.execute(select(Order.order_no, Order.id)).all())

        items = []
        for row in data["order_items"]:
            unit_price = money(row["price_per_unit"])
            product_id = product_ids[row["product_id"]]
            product_cost = connection.scalar(select(Product.unit_cost).where(Product.id == product_id))
            items.append({
                "id": row["order_item_id"], "order_id": order_ids[row["order_id"]], "product_id": product_id,
                "quantity": row["quantity"], "unit_price": unit_price, "unit_cost": product_cost,
                "discount_amount": Decimal(0), "line_amount": (unit_price * row["quantity"]).quantize(CENT),
            })
        statement = insert(OrderItem).values(items)
        connection.execute(statement.on_conflict_do_update(
            constraint="uq_order_items_order_product",
            set_={name: getattr(statement.excluded, name) for name in ("quantity", "unit_price", "unit_cost", "discount_amount", "line_amount")},
        ))
        counts = {table: connection.scalar(select(func.count()).select_from(model)) for table, model in {
            "customers": Customer, "products": Product, "orders": Order, "order_items": OrderItem
        }.items()}
    return {key: int(value or 0) for key, value in counts.items()}


def target_counts() -> dict[str, int]:
    with get_engine().connect() as connection:
        return {name: int(connection.scalar(select(func.count()).select_from(model)) or 0) for name, model in {
            "customers": Customer, "products": Product, "orders": Order, "order_items": OrderItem
        }.items()}


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=settings.legacy_sqlite_path)
    parser.add_argument("--dry-run", action="store_true", help="Validate source without writing PostgreSQL")
    parser.add_argument("--validate-only", action="store_true", help="Compare counts without writing")
    args = parser.parse_args()
    data = read_source(args.source)
    before = {table: len(rows) for table, rows in data.items()}
    print(f"SQLite counts: {before}")
    if args.dry_run:
        print("Dry run passed; PostgreSQL was not modified")
        return
    if args.validate_only:
        print(f"PostgreSQL counts: {target_counts()}")
        return
    print(f"PostgreSQL counts before: {target_counts()}")
    print(f"PostgreSQL counts after: {migrate(data)}")
    print("SQLite migration committed successfully")


if __name__ == "__main__":
    main()
