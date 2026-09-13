"""Generate and load deterministic ShopPulse business data."""

import argparse
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.engine import make_url

from shoppulse.data.generator import GenerationConfig, build_dataset, dataset_fingerprint
from shoppulse.db.models import (
    Customer, InventorySnapshot, MarketingCampaign, Order, OrderItem, Product, Refund, UserEvent,
)
from shoppulse.db.session import get_engine
from shoppulse.settings import get_settings

MODELS = {
    "customers": Customer, "products": Product, "marketing_campaigns": MarketingCampaign,
    "orders": Order, "order_items": OrderItem, "refunds": Refund,
    "inventory_snapshots": InventorySnapshot, "user_events": UserEvent,
}


def batches(rows: list[dict[str, Any]], size: int = 2_000) -> Iterable[list[dict[str, Any]]]:
    for offset in range(0, len(rows), size):
        yield rows[offset:offset + size]


def validate_reset_target(database_url: str, app_env: str, confirmation: str | None) -> str:
    url = make_url(database_url)
    database = url.database or ""
    if app_env.lower() in {"production", "prod"}:
        raise RuntimeError("Refusing to reset when APP_ENV is production")
    if database not in {"shoppulse", "shoppulse_dev", "shoppulse_test"}:
        raise RuntimeError(f"Refusing to reset unapproved database name: {database!r}")
    if confirmation != database:
        raise RuntimeError(f"Reset requires --confirm-reset {database}")
    return database


def load_dataset(dataset: dict[str, list[dict[str, Any]]], *, reset: bool, confirmation: str | None) -> dict[str, int]:
    settings = get_settings()
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Synthetic business data can only be loaded into PostgreSQL")
    with engine.begin() as connection:
        existing = int(connection.scalar(select(func.count()).select_from(Customer)) or 0)
        if existing and not reset:
            raise RuntimeError("Target contains data; rerun with --reset and the explicit database confirmation")
        if reset:
            validate_reset_target(settings.database_url, settings.app_env, confirmation)
            for model in reversed(list(MODELS.values())):
                connection.execute(delete(model))
        for name, model in MODELS.items():
            for batch in batches(dataset[name]):
                connection.execute(insert(model), batch)
        # Explicit IDs are part of the deterministic dataset; advance PostgreSQL sequences.
        for model in MODELS.values():
            table = model.__tablename__
            connection.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE(MAX(id),1), MAX(id) IS NOT NULL) FROM {table}"
            ))
        return {name: int(connection.scalar(select(func.count()).select_from(model)) or 0) for name, model in MODELS.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customers", type=int, default=2_000)
    parser.add_argument("--products", type=int, default=200)
    parser.add_argument("--orders", type=int, default=20_000)
    parser.add_argument("--campaigns", type=int, default=30)
    parser.add_argument("--events", type=int, default=200_000)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--preview", action="store_true", help="Generate and hash data without database writes")
    parser.add_argument("--reset", action="store_true", help="Delete existing business rows before loading")
    parser.add_argument("--confirm-reset", help="Must exactly equal the target database name")
    args = parser.parse_args()
    config = GenerationConfig(
        customers=args.customers, products=args.products, orders=args.orders,
        campaigns=args.campaigns, events=args.events, months=args.months, seed=args.seed,
    )
    dataset = build_dataset(config)
    counts = {name: len(rows) for name, rows in dataset.items()}
    print(f"Generated counts: {counts}")
    print(f"Deterministic fingerprint: {dataset_fingerprint(dataset)}")
    if args.preview:
        print("Preview complete; database was not modified")
        return
    print(f"Loaded counts: {load_dataset(dataset, reset=args.reset, confirmation=args.confirm_reset)}")


if __name__ == "__main__":
    main()
