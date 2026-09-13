import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError


TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is not configured")


@pytest.fixture(scope="module", autouse=True)
def configured_test_database():
    url = make_url(TEST_URL)
    if not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL database name must end with _test")
    os.environ["DATABASE_URL"] = TEST_URL
    os.environ["APP_ENV"] = "test"
    from shoppulse.settings import get_settings
    from shoppulse.db.session import _engine_for_url
    get_settings.cache_clear()
    _engine_for_url.cache_clear()
    yield


@pytest.mark.postgres
def test_connection_and_alembic_upgrade_from_empty_database():
    from shoppulse.db.session import health_check
    assert health_check()
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.mark.postgres
def test_sqlite_migration_is_idempotent_and_tools_query_postgres():
    from shoppulse.cli.migrate_sqlite import migrate, read_source
    from tools.database import get_order_status
    source = read_source(Path("data/structured/techhub.db"))
    first = migrate(source)
    second = migrate(source)
    assert first == second == {"customers": 50, "products": 25, "orders": 250, "order_items": 439}
    assert "Order ORD-" in get_order_status.invoke({"order_id": source["orders"][0]["order_id"]})


@pytest.mark.postgres
def test_small_synthetic_dataset_constraints_and_quality():
    from shoppulse.cli.data_quality import run_checks
    from shoppulse.cli.generate_data import load_dataset
    from shoppulse.data.generator import GenerationConfig, build_dataset
    database = make_url(TEST_URL).database
    data = build_dataset(GenerationConfig(customers=40, products=15, orders=120, campaigns=4, events=700, months=3, seed=99))
    counts = load_dataset(data, reset=True, confirmation=database)
    assert counts["orders"] == 120
    report = run_checks()
    assert report["passed"], report


@pytest.mark.postgres
def test_database_enforces_unique_and_foreign_key_constraints():
    from shoppulse.db.session import get_engine
    engine = get_engine()
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO customers
                  (id,customer_code,name,email,gender,segment,region,province,city,registration_channel,registered_at)
                SELECT 999999,customer_code,'Duplicate','duplicate@example.test','unknown',segment,region,province,city,
                       registration_channel,registered_at FROM customers LIMIT 1
            """))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO order_items
                  (id,order_id,product_id,quantity,unit_price,unit_cost,discount_amount,line_amount)
                VALUES (999999, -1, 1, 1, 10, 5, 0, 10)
            """))


@pytest.mark.postgres
def test_read_only_executor_caps_rows_and_rejects_writes():
    from shoppulse.db.session import get_engine
    from shoppulse.db.sql_safety import UnsafeSQLError, execute_read_only
    with get_engine().connect() as connection:
        result = execute_read_only(connection, "SELECT generate_series(1, 500) AS n", max_rows=25, timeout_ms=1000)
    assert len(result.rows) == 25
    assert result.truncated
    with get_engine().connect() as connection, pytest.raises(UnsafeSQLError):
        execute_read_only(connection, "DELETE FROM customers")
