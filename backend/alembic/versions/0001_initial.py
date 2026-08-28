"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            username VARCHAR(64) NOT NULL UNIQUE,
            display_name VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_users_username ON users (username)")

    op.execute(
        """
        CREATE TABLE transactions (
            id VARCHAR(32) PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            type VARCHAR(32) NOT NULL,
            product VARCHAR(32) NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            status VARCHAR(16) NOT NULL,
            failure_reason VARCHAR(256),
            payment_method VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_transactions_user_id ON transactions (user_id)")

    op.execute(
        """
        CREATE TABLE support_articles (
            id SERIAL PRIMARY KEY,
            question VARCHAR(512) NOT NULL,
            answer VARCHAR(4096) NOT NULL,
            category VARCHAR(64),
            tags JSON,
            embedding VECTOR(1536) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS support_articles")
    op.execute("DROP INDEX IF EXISTS ix_transactions_user_id")
    op.execute("DROP TABLE IF EXISTS transactions")
    op.execute("DROP INDEX IF EXISTS ix_users_username")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP EXTENSION IF EXISTS vector")
