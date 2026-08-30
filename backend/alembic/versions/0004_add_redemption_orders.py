"""add redemption orders

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE redemption_orders (
            id UUID PRIMARY KEY,
            txn_id VARCHAR(32) NOT NULL UNIQUE,
            user_id UUID NOT NULL REFERENCES users(id),
            product_name VARCHAR(128) NOT NULL,
            product_type VARCHAR(32) NOT NULL,
            metal_type VARCHAR(32) NOT NULL,
            quantity_purchased NUMERIC(12, 4) NOT NULL,
            txn_status VARCHAR(32) NOT NULL,
            awb_number VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_redemption_orders_user_id ON redemption_orders (user_id)")
    op.execute("CREATE INDEX ix_redemption_orders_awb_number ON redemption_orders (awb_number)")
    op.execute(
        "CREATE INDEX ix_redemption_orders_user_status_created "
        "ON redemption_orders (user_id, txn_status, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_redemption_orders_user_status_created")
    op.execute("DROP INDEX IF EXISTS ix_redemption_orders_awb_number")
    op.execute("DROP INDEX IF EXISTS ix_redemption_orders_user_id")
    op.execute("DROP TABLE IF EXISTS redemption_orders")
