"""Create ShopPulse phase-one schema and analytical views."""

from alembic import op

from shoppulse.db.base import Base
from shoppulse.db import models  # noqa: F401
from shoppulse.db.views import VIEW_DEFINITIONS

revision = "20260804_0001"
down_revision = None
branch_labels = None
depends_on = None

PHASE_ONE_TABLE_NAMES = (
    "customers",
    "products",
    "marketing_campaigns",
    "orders",
    "order_items",
    "refunds",
    "inventory_snapshots",
    "user_events",
)


def _phase_one_tables():
    """Keep this historical migration isolated from tables added in later phases."""
    return [Base.metadata.tables[name] for name in PHASE_ONE_TABLE_NAMES]


def upgrade() -> None:
    # The initial revision is intentionally derived from the frozen phase-one metadata.
    Base.metadata.create_all(
        bind=op.get_bind(), tables=_phase_one_tables(), checkfirst=False
    )
    for sql in VIEW_DEFINITIONS.values():
        op.execute(sql)


def downgrade() -> None:
    for view_name in reversed(VIEW_DEFINITIONS):
        op.execute(f"DROP VIEW IF EXISTS {view_name}")
    Base.metadata.drop_all(
        bind=op.get_bind(), tables=list(reversed(_phase_one_tables())), checkfirst=True
    )
