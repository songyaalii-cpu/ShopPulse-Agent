"""Add persistent sessions, analysis runs, events, and evaluations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260806_0002"
down_revision = "20260804_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("user_id", sa.String(64)),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"])
    op.create_index("ix_agent_sessions_last_activity", "agent_sessions", ["last_activity_at"])
    op.create_index("ix_agent_sessions_created_at", "agent_sessions", ["created_at"])

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("agent_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("intent", sa.String(48)),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("result_payload", postgresql.JSONB()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("worker_id", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_name", sa.String(128)),
        sa.Column("model_provider", sa.String(64)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cached_input_tokens", sa.Integer()),
        sa.Column("reasoning_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("estimated_cost", sa.Numeric(18, 8)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('queued','running','completed','failed','cancelled')", name="ck_analysis_runs_status"),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_runs_session_idempotency"),
    )
    op.create_index("ix_analysis_runs_run_id", "analysis_runs", ["run_id"])
    op.create_index("ix_analysis_runs_session_created", "analysis_runs", ["session_id", "created_at"])
    op.create_index("ix_analysis_runs_status_created", "analysis_runs", ["status", "created_at"])
    op.create_index("ix_analysis_runs_lease", "analysis_runs", ["status", "lease_expires_at"])

    op.create_table(
        "analysis_run_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False, unique=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("node_name", sa.String(96)),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_events_run_sequence"),
    )
    op.create_index("ix_run_events_run_created", "analysis_run_events", ["run_id", "created_at"])
    op.create_index("ix_run_events_type", "analysis_run_events", ["event_type"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("evaluation_id", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("dataset_name", sa.String(128), nullable=False),
        sa.Column("sample_limit", sa.Integer()),
        sa.Column("report_payload", postgresql.JSONB()),
        sa.Column("error_message", sa.String(500)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('queued','running','completed','failed')", name="ck_evaluation_runs_status"),
    )
    op.create_index("ix_evaluation_runs_created", "evaluation_runs", ["created_at"])


def downgrade() -> None:
    op.drop_table("evaluation_runs")
    op.drop_table("analysis_run_events")
    op.drop_table("analysis_runs")
    op.drop_table("agent_sessions")
