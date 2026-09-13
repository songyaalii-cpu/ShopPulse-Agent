"""LangChain-compatible wrappers around deterministic analytics services."""

from langchain.tools import tool

from shoppulse.analytics.cohort import cohort_retention
from shoppulse.analytics.funnel import funnel_analysis
from shoppulse.analytics.metrics import metric_trend
from shoppulse.analytics.rfm import rfm_segments
from shoppulse.analytics.weekly_report import weekly_report


@tool
def get_kpi_trends() -> dict:
    """Return the canonical KPI trend over the default twelve-week business period."""
    return metric_trend()


@tool
def get_rfm_segments() -> dict:
    """Return deterministic RFM customer segments without customer PII."""
    return rfm_segments()


@tool
def get_cohort_retention() -> dict:
    """Return monthly M0-M11 new-customer retention cohorts."""
    return cohort_retention()


@tool
def get_behavior_funnel() -> dict:
    """Return a session-deduplicated view-to-purchase funnel."""
    return funnel_analysis()


@tool
def get_weekly_report() -> dict:
    """Return the latest complete deterministic weekly operations report."""
    return weekly_report()
