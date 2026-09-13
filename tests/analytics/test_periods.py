from datetime import date

import pytest

from shoppulse.analytics.periods import complete_week_end, previous_period
from shoppulse.analytics.schemas import DatePeriod


def test_complete_week_and_previous_period_are_contiguous():
    assert complete_week_end(date(2026, 8, 5)) == date(2026, 8, 2)
    current = DatePeriod(start=date(2026, 7, 27), end=date(2026, 8, 2), granularity="week")
    previous = previous_period(current)
    assert previous.start == date(2026, 7, 20)
    assert previous.end == date(2026, 7, 26)


def test_period_rejects_reverse_range():
    with pytest.raises(ValueError):
        DatePeriod(start=date(2026, 8, 2), end=date(2026, 7, 1))
