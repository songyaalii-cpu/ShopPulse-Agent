"""Centralized business-date handling for synthetic and production datasets."""

from datetime import date, timedelta

from sqlalchemy import Engine, text

from shoppulse.analytics.schemas import DatePeriod, Granularity
from shoppulse.db.session import get_engine


def data_max_date(engine: Engine | None = None) -> date:
    db = engine or get_engine()
    statement = text("""
        SELECT GREATEST(
            COALESCE((SELECT MAX(ordered_at)::date FROM orders), DATE '1970-01-01'),
            COALESCE((SELECT MAX(occurred_at)::date FROM user_events), DATE '1970-01-01')
        )
    """)
    with db.connect() as connection:
        value = connection.scalar(statement)
    if value == date(1970, 1, 1):
        raise ValueError("business database contains no orders or events")
    return value


def complete_week_end(max_date: date) -> date:
    """Return the latest Sunday on or before the data maximum date."""
    return max_date - timedelta(days=(max_date.weekday() + 1) % 7)


def resolve_period(
    start: date | None = None,
    end: date | None = None,
    granularity: Granularity = "week",
    engine: Engine | None = None,
    default_weeks: int = 12,
) -> DatePeriod:
    if granularity not in {"day", "week", "month"}:
        raise ValueError(f"unsupported granularity: {granularity}")
    maximum = data_max_date(engine)
    resolved_end = end or maximum
    if resolved_end > maximum:
        raise ValueError(f"end date {resolved_end} is after data maximum {maximum}")
    resolved_start = start or (resolved_end - timedelta(weeks=default_weeks) + timedelta(days=1))
    if resolved_start > resolved_end:
        raise ValueError("start date must be on or before end date")
    return DatePeriod(start=resolved_start, end=resolved_end, granularity=granularity)


def previous_period(period: DatePeriod) -> DatePeriod:
    days = (period.end - period.start).days + 1
    previous_end = period.start - timedelta(days=1)
    return DatePeriod(
        start=previous_end - timedelta(days=days - 1),
        end=previous_end,
        granularity=period.granularity,
    )
