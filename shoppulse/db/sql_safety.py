"""Strict read-only execution boundary for generated Text-to-SQL."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from sqlglot import exp, parse
from sqlglot.errors import ParseError


class UnsafeSQLError(ValueError):
    """Raised when SQL is not a single, read-only query."""


@dataclass(frozen=True)
class ReadOnlyResult:
    rows: list[dict[str, Any]]
    truncated: bool
    max_rows: int


_MUTATING_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Command,
    exp.Copy,
    exp.Merge,
    exp.Transaction,
)
_BLOCKED_FUNCTIONS = {"pg_sleep", "pg_terminate_backend", "pg_cancel_backend", "dblink"}


def validate_read_only_sql(query: str) -> str:
    """Return stripped SQL if it is one SELECT/CTE/UNION statement.

    Parsing the AST avoids keyword checks that are fooled by comments, casing, CTEs,
    or strings. Parameters remain the responsibility of SQLAlchemy's ``text`` bind API.
    """
    candidate = query.strip().rstrip(";").strip()
    if not candidate:
        raise UnsafeSQLError("SQL query is empty")
    try:
        statements = [statement for statement in parse(candidate, read="postgres") if statement]
    except ParseError as exc:
        raise UnsafeSQLError(f"SQL parse error: {exc}") from exc
    if len(statements) != 1:
        raise UnsafeSQLError("Exactly one SQL statement is allowed")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise UnsafeSQLError("Only SELECT queries are allowed")
    for node in statement.walk():
        if isinstance(node, _MUTATING_NODES):
            raise UnsafeSQLError(f"Forbidden SQL operation: {node.key.upper()}")
        if isinstance(node, exp.Into):
            raise UnsafeSQLError("SELECT INTO is forbidden")
        if isinstance(node, exp.Func):
            function_name = (getattr(node, "name", None) or node.sql_name()).lower()
            if function_name in _BLOCKED_FUNCTIONS:
                raise UnsafeSQLError(f"Forbidden SQL function: {function_name}")
        if isinstance(node, exp.Lock):
            raise UnsafeSQLError("Row-locking clauses are forbidden")
    return candidate


def execute_read_only(
    connection: Connection,
    query: str,
    parameters: dict[str, Any] | None = None,
    *,
    max_rows: int = 200,
    timeout_ms: int = 5000,
) -> ReadOnlyResult:
    """Execute safe dynamic SQL in a read-only transaction with hard limits."""
    validated = validate_read_only_sql(query)
    if connection.dialect.name != "postgresql":
        raise RuntimeError("The Text-to-SQL execution boundary requires PostgreSQL")
    if max_rows < 1 or timeout_ms < 1:
        raise ValueError("max_rows and timeout_ms must be positive")

    transaction = connection.begin()
    try:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        # PostgreSQL SET does not accept bind parameters; set_config does and stays local
        # to this transaction when its third argument is true.
        connection.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(timeout_ms)},
        )
        limited = f"SELECT * FROM ({validated}) AS shoppulse_readonly_query LIMIT {max_rows + 1}"
        result = connection.execute(text(limited), parameters or {})
        mappings: list[RowMapping] = list(result.mappings().fetchmany(max_rows + 1))
        transaction.commit()
    except Exception:
        transaction.rollback()
        raise
    return ReadOnlyResult(
        rows=[dict(row) for row in mappings[:max_rows]],
        truncated=len(mappings) > max_rows,
        max_rows=max_rows,
    )
