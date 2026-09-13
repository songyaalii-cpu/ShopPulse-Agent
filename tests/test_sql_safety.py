import pytest

from shoppulse.db.sql_safety import UnsafeSQLError, validate_read_only_sql


@pytest.mark.parametrize("query", [
    "SELECT 1",
    "WITH totals AS (SELECT customer_id, sum(paid_amount) AS value FROM orders GROUP BY 1) SELECT * FROM totals",
    "SELECT 'DROP TABLE products' AS harmless_text",
    "SELECT * FROM products WHERE sku = :sku",
])
def test_allows_read_only_queries(query):
    assert validate_read_only_sql(query)


@pytest.mark.parametrize("query", [
    "INSERT INTO products (sku) VALUES ('x')",
    "UPDATE products SET status='inactive'",
    "DELETE FROM orders",
    "DROP TABLE customers",
    "ALTER TABLE orders ADD COLUMN x int",
    "TRUNCATE orders",
    "CREATE TABLE stolen(id int)",
    "GRANT SELECT ON orders TO public",
    "REVOKE SELECT ON orders FROM public",
    "COPY orders TO '/tmp/orders.csv'",
    "SELECT 1; DELETE FROM orders",
    "WITH gone AS (DELETE FROM orders RETURNING *) SELECT * FROM gone",
    "SELECT * FROM orders FOR UPDATE",
    "SELECT pg_sleep(10)",
])
def test_rejects_dangerous_sql(query):
    with pytest.raises(UnsafeSQLError):
        validate_read_only_sql(query)


def test_rejects_empty_and_malformed_sql():
    for query in ("", ";", "SELECT ("):
        with pytest.raises(UnsafeSQLError):
            validate_read_only_sql(query)
