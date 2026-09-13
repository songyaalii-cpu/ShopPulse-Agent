"""SQLAlchemy 2.0 models for the ShopPulse business database.

All timestamps are timezone-aware and stored by PostgreSQL as TIMESTAMPTZ. Application
code supplies UTC values; presentation layers may convert them to a business timezone.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shoppulse.db.base import Base

MONEY = Numeric(14, 2)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UpdatedTimestampMixin(TimestampMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Customer(UpdatedTimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("gender IN ('female','male','other','unknown')", name="ck_customers_gender"),
        Index("ix_customers_region_segment", "region", "segment"),
        Index("ix_customers_registered_at", "registered_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    gender: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    birth_date: Mapped[date | None] = mapped_column(Date)
    segment: Mapped[str] = mapped_column(String(32), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    province: Mapped[str] = mapped_column(String(64), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    registration_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Product(UpdatedTimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("list_price > 0 AND sale_price > 0 AND unit_cost >= 0", name="ck_products_prices_positive"),
        CheckConstraint("sale_price <= list_price", name="ck_products_sale_lte_list"),
        CheckConstraint("unit_cost <= sale_price", name="ck_products_cost_lte_sale"),
        CheckConstraint("status IN ('active','inactive','discontinued')", name="ck_products_status"),
        Index("ix_products_category_status", "category", "status"),
        Index("ix_products_brand", "brand"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sku: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    subcategory: Mapped[str] = mapped_column(String(64), nullable=False)
    brand: Mapped[str] = mapped_column(String(64), nullable=False)
    list_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    sale_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    launched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketingCampaign(TimestampMixin, Base):
    __tablename__ = "marketing_campaigns"
    __table_args__ = (
        CheckConstraint("budget >= 0", name="ck_campaigns_budget"),
        CheckConstraint("end_at > start_at", name="ck_campaigns_date_range"),
        CheckConstraint("status IN ('planned','active','completed','cancelled')", name="ck_campaigns_status"),
        Index("ix_campaigns_channel_dates", "channel", "start_at", "end_at"),
        Index("ix_campaigns_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(48), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    budget: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)


class Order(UpdatedTimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("order_amount >= 0 AND discount_amount >= 0 AND shipping_fee >= 0 AND paid_amount >= 0", name="ck_orders_amounts_nonnegative"),
        CheckConstraint("paid_amount = order_amount - discount_amount + shipping_fee", name="ck_orders_paid_formula"),
        CheckConstraint("status IN ('pending','paid','shipped','completed','cancelled')", name="ck_orders_status"),
        Index("ix_orders_customer_ordered", "customer_id", "ordered_at"),
        Index("ix_orders_channel_ordered", "channel", "ordered_at"),
        Index("ix_orders_status_ordered", "status", "ordered_at"),
        Index("ix_orders_region_ordered", "region", "ordered_at"),
        Index("ix_orders_campaign", "campaign_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("marketing_campaigns.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    order_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    shipping_fee: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer: Mapped[Customer] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(TimestampMixin, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        CheckConstraint("unit_price > 0 AND unit_cost >= 0 AND discount_amount >= 0 AND line_amount >= 0", name="ck_order_items_amounts"),
        CheckConstraint("line_amount = quantity * unit_price - discount_amount", name="ck_order_items_line_formula"),
        UniqueConstraint("order_id", "product_id", name="uq_order_items_order_product"),
        Index("ix_order_items_product_order", "product_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    line_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("refund_amount > 0", name="ck_refunds_amount"),
        CheckConstraint("status IN ('requested','approved','rejected','completed')", name="ck_refunds_status"),
        CheckConstraint("refund_type IN ('full','partial')", name="ck_refunds_type"),
        Index("ix_refunds_order_status", "order_id", "status"),
        Index("ix_refunds_customer_requested", "customer_id", "requested_at"),
        Index("ix_refunds_requested_at", "requested_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    refund_no: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    order_item_id: Mapped[int | None] = mapped_column(ForeignKey("order_items.id", ondelete="SET NULL"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(String(96), nullable=False)
    refund_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventorySnapshot(TimestampMixin, Base):
    __tablename__ = "inventory_snapshots"
    __table_args__ = (
        CheckConstraint("available_quantity >= 0 AND reserved_quantity >= 0 AND inbound_quantity >= 0", name="ck_inventory_nonnegative"),
        UniqueConstraint("product_id", "warehouse_code", "snapshot_date", name="uq_inventory_product_warehouse_date"),
        Index("ix_inventory_snapshot_date", "snapshot_date"),
        Index("ix_inventory_warehouse_date", "warehouse_code", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    warehouse_code: Mapped[str] = mapped_column(String(32), nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    inbound_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)


class UserEvent(TimestampMixin, Base):
    __tablename__ = "user_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('view','click','add_to_cart','checkout','purchase')", name="ck_events_type"),
        Index("ix_events_occurred_type", "occurred_at", "event_type"),
        Index("ix_events_customer_occurred", "customer_id", "occurred_at"),
        Index("ix_events_session_occurred", "session_id", "occurred_at"),
        Index("ix_events_product_occurred", "product_id", "occurred_at"),
        Index("ix_events_campaign_occurred", "campaign_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("marketing_campaigns.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    device_type: Mapped[str] = mapped_column(String(24), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class AgentSession(UpdatedTimestampMixin, Base):
    """Persistent conversation container; deliberately contains no customer PII."""

    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("ix_agent_sessions_last_activity", "last_activity_at"),
        Index("ix_agent_sessions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class AnalysisRun(UpdatedTimestampMixin, Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled')",
            name="ck_analysis_runs_status",
        ),
        UniqueConstraint("session_id", "idempotency_key", name="uq_runs_session_idempotency"),
        Index("ix_analysis_runs_session_created", "session_id", "created_at"),
        Index("ix_analysis_runs_status_created", "status", "created_at"),
        Index("ix_analysis_runs_lease", "status", "lease_expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="queued")
    intent: Mapped[str | None] = mapped_column(String(48))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    model_name: Mapped[str | None] = mapped_column(String(128))
    model_provider: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cache_hit: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    session: Mapped[AgentSession] = relationship(back_populates="runs")
    events: Mapped[list["AnalysisRunEvent"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class AnalysisRunEvent(TimestampMixin, Base):
    __tablename__ = "analysis_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_events_run_sequence"),
        Index("ix_run_events_run_created", "run_id", "created_at"),
        Index("ix_run_events_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(96))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    run: Mapped[AnalysisRun] = relationship(back_populates="events")


class EvaluationRun(UpdatedTimestampMixin, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','failed')", name="ck_evaluation_runs_status"),
        Index("ix_evaluation_runs_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="queued")
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    sample_limit: Mapped[int | None] = mapped_column(Integer)
    report_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(String(500))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
