"""merge redemption_orders into transactions

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-31

Adds the columns needed to represent a REDEMPTION-type transaction, widens
a couple of existing columns to fit the new data, relaxes NOT NULL on
columns that don't apply to a REDEMPTION row, backfills every existing
redemption_orders row into transactions as type='REDEMPTION', and renames
the old branded product names to their plain form (folded in here rather
than a separate migration, since this hadn't shipped to the cloud DB yet at
the time of the rename - the exact old/new values are in the UPDATE
statements below).

Deliberately does NOT drop redemption_orders - that's a separate follow-up
migration, landed only after the new columns have been verified in place.
Every step here is additive, backfill, or a safe rename; nothing here can
lose data, and the backfill step is guarded to be a safe no-op if
redemption_orders no longer exists (e.g. this migration is re-run after a
later migration already dropped it).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS awb_number VARCHAR(64)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS product_type VARCHAR(32)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS metal_type VARCHAR(32)")
    op.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS quantity NUMERIC(12, 4)")
    op.execute(
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS related_transaction_id VARCHAR(32) "
        "REFERENCES transactions(id)"
    )

    op.execute("ALTER TABLE transactions ALTER COLUMN status TYPE VARCHAR(32)")
    op.execute("ALTER TABLE transactions ALTER COLUMN product TYPE VARCHAR(64)")
    op.execute("ALTER TABLE transactions ALTER COLUMN payment_method DROP NOT NULL")
    op.execute("ALTER TABLE transactions ALTER COLUMN amount DROP NOT NULL")

    # Backfill: one INSERT ... SELECT per existing redemption_orders row.
    # Guarded so re-running this migration after 0006 has already dropped
    # redemption_orders is a safe no-op rather than an error. related_transaction_id
    # is intentionally left NULL here - a legacy redemption_orders.txn_id was always
    # just a free-text label, never a real FK, so there's no reliable way to infer
    # which historical BUY it actually redeemed. Only freshly-reseeded demo data
    # (via scripts/seed.py) gets a real related_transaction_id going forward.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('redemption_orders') IS NOT NULL THEN
                INSERT INTO transactions (
                    id, user_id, type, product, amount, status, failure_reason,
                    payment_method, awb_number, product_type, metal_type, quantity,
                    related_transaction_id, created_at, updated_at
                )
                SELECT
                    'rdm_' || substr(replace(id::text, '-', ''), 1, 28), user_id, 'REDEMPTION',
                    product_name, NULL, txn_status, NULL,
                    NULL, awb_number, product_type, metal_type, quantity_purchased,
                    NULL, created_at, updated_at
                FROM redemption_orders
                WHERE NOT EXISTS (
                    SELECT 1 FROM transactions t
                    WHERE t.id = 'rdm_' || substr(replace(redemption_orders.id::text, '-', ''), 1, 28)
                );
            END IF;
        END $$;
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_transactions_awb_number ON transactions (awb_number)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_transactions_user_type_status_created "
        "ON transactions (user_id, type, status, created_at DESC)"
    )

    op.execute("UPDATE transactions SET product = 'Gold Bar' WHERE product = 'Aura Gold Bar' AND type = 'REDEMPTION'")
    op.execute("UPDATE transactions SET product = 'Gold Coin' WHERE product = 'Aura Gold Coin' AND type = 'REDEMPTION'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_transactions_user_type_status_created")
    op.execute("DROP INDEX IF EXISTS ix_transactions_awb_number")
    op.execute("DELETE FROM transactions WHERE type = 'REDEMPTION'")
    op.execute("ALTER TABLE transactions ALTER COLUMN amount SET NOT NULL")
    op.execute("ALTER TABLE transactions ALTER COLUMN payment_method SET NOT NULL")
    op.execute("ALTER TABLE transactions ALTER COLUMN product TYPE VARCHAR(32)")
    op.execute("ALTER TABLE transactions ALTER COLUMN status TYPE VARCHAR(16)")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS related_transaction_id")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS quantity")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS metal_type")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS product_type")
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS awb_number")
