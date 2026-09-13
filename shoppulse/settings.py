"""Environment-backed settings for business and LangGraph databases."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://shoppulse:shoppulse_local_only@localhost:5432/shoppulse"
    # Reserved only: checkpoint/memory integration is deliberately out of phase-one scope.
    langgraph_database_url: str | None = None
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout_seconds: int = Field(default=30, ge=1)
    sql_query_timeout_ms: int = Field(default=5000, ge=100, le=60000)
    sql_max_rows: int = Field(default=200, ge=1, le=5000)
    legacy_sqlite_path: Path = Path("data/structured/techhub.db")
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "shoppulse:"
    workshop_model: str | None = None
    llm_enabled: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    frontend_origin: str = "http://localhost:3000"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    log_level: str = "INFO"
    sse_heartbeat_seconds: int = Field(default=15, ge=1, le=120)
    sse_stream_ttl_seconds: int = Field(default=3600, ge=60)
    sse_stream_max_length: int = Field(default=1000, ge=10, le=10000)
    sse_event_max_bytes: int = Field(default=65536, ge=1024)
    run_timeout_seconds: int = Field(default=180, ge=10, le=3600)
    run_max_retries: int = Field(default=2, ge=0, le=10)
    run_lease_seconds: int = Field(default=240, ge=30, le=7200)
    worker_concurrency: int = Field(default=2, ge=1, le=32)
    analysis_cache_ttl_seconds: int = Field(default=600, ge=0)
    token_pricing_config: Path = Path("shoppulse/evals/pricing.json")
    max_request_body_bytes: int = Field(default=65536, ge=1024)
    max_query_length: int = Field(default=2000, ge=20, le=10000)
    max_filters: int = Field(default=10, ge=0, le=50)
    submit_rate_limit_per_minute: int = Field(default=30, ge=1, le=1000)
    demo_user_id: str = "local-demo"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.is_production:
            insecure = "shoppulse_local_only" in self.database_url
            if insecure or self.demo_user_id == "local-demo":
                raise ValueError("production requires explicit database credentials and DEMO_USER_ID")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
