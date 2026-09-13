from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from shoppulse.cli.migrate_sqlite import read_source
from shoppulse.db.base import Base
from shoppulse.db import models  # noqa: F401


def test_all_required_models_compile_for_postgresql():
    required = {
        "customers", "products", "orders", "order_items", "refunds",
        "inventory_snapshots", "marketing_campaigns", "user_events",
    }
    assert required <= set(Base.metadata.tables)
    assert {"agent_sessions", "analysis_runs", "analysis_run_events", "evaluation_runs"} <= set(Base.metadata.tables)
    for table in Base.metadata.sorted_tables:
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_legacy_sqlite_source_validates_and_retains_expected_counts():
    data = read_source(Path("data/structured/techhub.db"))
    assert {name: len(rows) for name, rows in data.items()} == {
        "customers": 50, "products": 25, "orders": 250, "order_items": 439,
    }
