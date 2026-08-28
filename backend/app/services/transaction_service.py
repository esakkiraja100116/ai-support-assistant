from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transaction, User


def get_recent_transactions(db: Session, user: User, limit: int = 10) -> list[Transaction]:
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def get_transaction_details(db: Session, user: User, transaction_id: str) -> Transaction | None:
    """Returns None (never another user's row) if the transaction doesn't
    exist or doesn't belong to `user`. Callers should map that to a 404,
    not a 403, so we don't confirm the id exists for someone else."""
    stmt = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.user_id == user.id,
    )
    return db.scalars(stmt).first()
