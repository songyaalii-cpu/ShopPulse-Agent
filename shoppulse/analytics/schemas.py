"""Typed contracts shared by analytics services and graph nodes."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Granularity = Literal["day", "week", "month"]
AnalysisIntent = Literal[
    "trend", "rfm", "cohort", "funnel", "attribution", "weekly_report",
    "inventory", "association",
]


class DatePeriod(BaseModel):
    start: date
    end: date
    granularity: Granularity = "week"

    @model_validator(mode="after")
    def validate_range(self):
        if self.start > self.end:
            raise ValueError("start must be on or before end")
        return self


class AnalysisRequest(BaseModel):
    original_query: str
    intent: AnalysisIntent = "trend"
    metrics: list[str] = Field(default_factory=lambda: ["gmv", "order_count", "average_order_value"])
    start_date: date | None = None
    end_date: date | None = None
    granularity: Granularity = "week"
    comparison: Literal["previous_period", "year_over_year", "custom"] = "previous_period"
    filters: dict[str, str] = Field(default_factory=dict)
    dimensions: list[str] = Field(default_factory=list)
    detect_anomalies: bool = False
    require_attribution: bool = False
    generate_report: bool = False


class AnalysisResponse(BaseModel):
    summary: str
    period: DatePeriod | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    trend: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    attributions: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime


class NarrativeOutput(BaseModel):
    summary: str
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
