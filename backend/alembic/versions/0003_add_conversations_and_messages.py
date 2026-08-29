"""add conversations and messages

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversations (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            title VARCHAR(256) NOT NULL,
            total_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
            models_used VARCHAR(256),
            message_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_conversations_user_id ON conversations (user_id)")

    op.execute(
        """
        CREATE TABLE messages (
            id UUID PRIMARY KEY,
            conversation_id UUID NOT NULL REFERENCES conversations(id),
            role VARCHAR(16) NOT NULL,
            content VARCHAR(4096) NOT NULL,
            response_type VARCHAR(32),
            response_data JSON,
            model_used VARCHAR(128),
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            cost_usd NUMERIC(12, 6),
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_messages_conversation_id ON messages (conversation_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_conversation_id")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP INDEX IF EXISTS ix_conversations_user_id")
    op.execute("DROP TABLE IF EXISTS conversations")
