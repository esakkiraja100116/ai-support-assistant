"""add user role

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'USER'")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN role")
