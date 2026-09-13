"""Monthly first-purchase cohort retention."""

from typing import Any

from sqlalchemy import Engine, text

from shoppulse.analytics.periods import data_max_date
from shoppulse.db.session import get_engine


def cohort_retention(
    engine: Engine | None = None,
    months: int = 12,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not 1 <= months <= 24:
        raise ValueError("months must be between 1 and 24")
    db = engine or get_engine()
    selected = filters or {}
    allowed = {"registration_channel", "region", "first_order_channel"}
    unknown = set(selected) - allowed
    if unknown:
        raise ValueError(f"unsupported cohort filters: {sorted(unknown)}")
    clauses: list[str] = []
    params: dict[str, Any] = {"max_index": months - 1}
    for name, value in selected.items():
        column = {"registration_channel": "registration_channel", "region": "region", "first_order_channel": "first_order_channel"}[name]
        clauses.append(f"{column} = :{name}")
        params[name] = value
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    statement = text(f"""
        WITH valid_orders AS (
            SELECT o.customer_id, o.ordered_at, o.channel,
                   ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.ordered_at, o.id) AS rn
            FROM orders o WHERE o.status <> 'cancelled' AND o.paid_at IS NOT NULL
        ), customer_cohort AS (
            SELECT c.id AS customer_id, c.registration_channel, c.region,
                   date_trunc('month', MIN(v.ordered_at))::date AS cohort_month,
                   MAX(v.channel) FILTER (WHERE v.rn=1) AS first_order_channel
            FROM customers c JOIN valid_orders v ON v.customer_id=c.id
            GROUP BY c.id, c.registration_channel, c.region
        ), filtered AS (
            SELECT * FROM customer_cohort {where}
        ), activity AS (
            SELECT f.cohort_month, date_trunc('month', o.ordered_at)::date AS activity_month,
                   ((EXTRACT(YEAR FROM age(date_trunc('month', o.ordered_at), f.cohort_month))*12
                     + EXTRACT(MONTH FROM age(date_trunc('month', o.ordered_at), f.cohort_month)))::int) AS cohort_index,
                   COUNT(DISTINCT o.customer_id) AS active_customers
            FROM filtered f JOIN orders o ON o.customer_id=f.customer_id
            WHERE o.status <> 'cancelled' AND o.paid_at IS NOT NULL
            GROUP BY f.cohort_month, activity_month, cohort_index
        ), sizes AS (
            SELECT cohort_month, COUNT(*) AS cohort_size FROM filtered GROUP BY cohort_month
        )
        SELECT a.cohort_month, a.cohort_index, a.active_customers, s.cohort_size,
               a.active_customers::numeric/s.cohort_size AS retention_rate
        FROM activity a JOIN sizes s USING(cohort_month)
        WHERE a.cohort_index BETWEEN 0 AND :max_index
        ORDER BY a.cohort_month, a.cohort_index
    """)
    with db.connect() as connection:
        raw = [dict(row) for row in connection.execute(statement, params).mappings()]
    maximum = data_max_date(db)
    cohorts: dict[str, dict[str, Any]] = {}
    for row in raw:
        key = row["cohort_month"].isoformat()
        cohort = cohorts.setdefault(key, {"cohort_month": key, "cohort_size": row["cohort_size"], "retention": {}})
        cohort["retention"][f"M{row['cohort_index']}"] = {
            "customers": row["active_customers"], "rate": float(row["retention_rate"])
        }
    for cohort in cohorts.values():
        year, month, _ = map(int, cohort["cohort_month"].split("-"))
        for index in range(months):
            observable_month = year * 12 + month - 1 + index
            max_month = maximum.year * 12 + maximum.month - 1
            key = f"M{index}"
            if key not in cohort["retention"]:
                cohort["retention"][key] = None if observable_month > max_month else {"customers": 0, "rate": 0.0}
    ordered = sorted(cohorts.values(), key=lambda item: item["cohort_month"])
    return {
        "data_max_date": maximum.isoformat(),
        "filters": selected,
        "cohorts": ordered,
        "new_customer_trend": [
            {"cohort_month": item["cohort_month"], "customers": item["cohort_size"]} for item in ordered
        ],
        "m1_retention_trend": [
            {"cohort_month": item["cohort_month"], "retention": item["retention"].get("M1")}
            for item in ordered
        ],
    }
