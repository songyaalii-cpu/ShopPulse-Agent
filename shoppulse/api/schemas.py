from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool = False


class SessionCreate(BaseModel):
    title: str = Field(default="新分析", min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionOut(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    metadata: dict[str, Any]


class RunCreate(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    metrics: list[str] = Field(default_factory=list, max_length=10)
    dimensions: list[str] = Field(default_factory=list, max_length=10)
    filters: dict[str, str] = Field(default_factory=dict)
    output_format: Literal["structured", "markdown"] = "structured"
    llm_enabled: bool = False


class RunSummary(BaseModel):
    run_id: str
    session_id: str
    status: str
    query: str
    intent: str | None
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    events_url: str
    latency_ms: int | None
    token_usage: dict[str, Any]
    estimated_cost: float | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class Page(BaseModel):
    items: list[Any]
    page: int
    page_size: int
    total: int


class EvaluationCreate(BaseModel):
    dataset_name: str = "phase3-72"
    sample_limit: int | None = Field(default=None, ge=1, le=100)


class EvaluationOut(BaseModel):
    evaluation_id: str
    status: str
    dataset_name: str
    sample_limit: int | None
    report: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
