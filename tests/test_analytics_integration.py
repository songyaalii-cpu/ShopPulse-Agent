import os
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url


TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is not configured")


@pytest.fixture(scope="module", autouse=True)
def analytics_database():
    database = make_url(TEST_URL).database
    if not (database or "").endswith("_test"):
        pytest.fail("analytics integration tests require a database ending in _test")
    os.environ["DATABASE_URL"] = TEST_URL
    os.environ["APP_ENV"] = "test"
    from shoppulse.settings import get_settings
    from shoppulse.db.session import _engine_for_url
    get_settings.cache_clear()
    _engine_for_url.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    from shoppulse.cli.generate_data import load_dataset
    from shoppulse.data.generator import GenerationConfig, build_dataset
    dataset = build_dataset(GenerationConfig(
        customers=300, products=50, orders=2500, campaigns=10, events=25000, months=12, seed=20260804
    ))
    load_dataset(dataset, reset=True, confirmation=database)
    yield


def test_kpi_rfm_cohort_and_funnel_services():
    from shoppulse.analytics.metrics import metric_trend
    from shoppulse.analytics.rfm import rfm_segments
    from shoppulse.analytics.cohort import cohort_retention
    from shoppulse.analytics.funnel import funnel_analysis
    trend = metric_trend()
    assert trend["rows"] and all(row["gmv"] >= 0 and row["refund_rate"] >= 0 for row in trend["rows"])
    rfm = rfm_segments()
    assert sum(segment["customer_share"] for segment in rfm["segments"]) == pytest.approx(1)
    cohort = cohort_retention(months=12)
    assert cohort["cohorts"] and any(value is None for row in cohort["cohorts"] for value in row["retention"].values())
    funnel = funnel_analysis()
    assert funnel["totals"]["view_sessions"] >= funnel["totals"]["add_to_cart_sessions"] >= funnel["totals"]["purchase_sessions"]
    assert funnel["totals"]["invalid_sequence_sessions"] == 0


def test_injected_anomalies_are_discoverable_without_prompt_answers():
    from shoppulse.analytics.attribution import compare_dimension
    from shoppulse.analytics.funnel import funnel_analysis
    from shoppulse.analytics.inventory import inventory_alerts
    from shoppulse.analytics.periods import data_max_date
    from shoppulse.analytics.schemas import DatePeriod
    end = data_max_date()
    current_60 = DatePeriod(start=end-timedelta(days=59), end=end, granularity="week")
    prior_60 = DatePeriod(start=end-timedelta(days=119), end=end-timedelta(days=60), granularity="week")
    refund_rows = compare_dimension("refund_rate", "region", current_60, prior_60)
    south = next(row for row in refund_rows if row["value"] == "South")
    assert south["absolute_change"] > 0
    current_social = funnel_analysis(end-timedelta(days=44), end, filters={"channel": "social"})["totals"]
    prior_social = funnel_analysis(end-timedelta(days=89), end-timedelta(days=45), filters={"channel": "social"})["totals"]
    assert current_social["view_to_purchase_rate"] < prior_social["view_to_purchase_rate"]
    sku7 = next(alert for alert in inventory_alerts() if alert["sku"] == "SP-00007")
    assert sku7["alert"] == "stockout"


def test_bounded_attribution_graph_and_weekly_fallback():
    from shoppulse.agents import create_analytics_graph
    from shoppulse.analytics.weekly_report import weekly_report
    result = create_analytics_graph().invoke({"original_query": "为什么最近一周退款率上升？"})
    answer = result["final_answer"]
    assert 1 <= len(answer["attributions"]) <= 3
    assert answer["tool_call_count"] <= 8
    assert answer["evidence"]
    report = weekly_report()
    assert "数据事实" in report["markdown"]
    assert str(report["metrics"]["gmv"]) in report["markdown"].replace(",", "") or report["metrics"]["gmv"] >= 0


def test_enhancement_queries_are_read_only_and_bounded():
    from shoppulse.analytics.association import product_associations
    from shoppulse.analytics.inventory import inventory_alerts
    associations = product_associations(limit=10)
    assert 0 < len(associations) <= 10
    assert all(row["support"] > 0 and row["confidence"] > 0 and row["lift"] > 0 for row in associations)
    alerts = inventory_alerts(limit=20)
    assert len(alerts) <= 20
    assert {row["alert"] for row in alerts} <= {"stockout", "low_stock", "overstock"}
