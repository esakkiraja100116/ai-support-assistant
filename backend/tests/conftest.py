import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://support:support@localhost:5433/support_assistant_test"
)
# Separate Redis DB index from the dev default (0), same idea as the test
# Postgres database being separate from the dev one - tests get a clean,
# isolated cache namespace rather than colliding with whatever's cached from
# manual local testing.
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models  # noqa: E402
from app.auth.security import create_access_token  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

TEST_DB_URL = settings.database_url
_ADMIN_DB_URL = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
_TEST_DB_NAME = TEST_DB_URL.rsplit("/", 1)[1]


def _ensure_test_database_exists() -> None:
    admin_engine = create_engine(_ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": _TEST_DB_NAME}
        ).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_TEST_DB_NAME}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    _ensure_test_database_exists()
    engine = create_engine(TEST_DB_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()
    yield


@pytest.fixture()
def db_session():
    engine = create_engine(TEST_DB_URL)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def make_user(db_session):
    def _make(username: str = "alice", display_name: str = "Alice", role: str = "USER") -> models.User:
        user = models.User(username=username, display_name=display_name, role=role)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture()
def make_transaction(db_session):
    def _make(
        user: models.User,
        txn_id: str,
        status: str = "SUCCESS",
        failure_reason: str | None = None,
        type: str = "BUY",
        product: str = "GOLD24",
        amount: float = 100,
        payment_method: str = "UPI",
    ) -> models.Transaction:
        txn = models.Transaction(
            id=txn_id,
            user_id=user.id,
            type=type,
            product=product,
            amount=amount,
            status=status,
            failure_reason=failure_reason,
            payment_method=payment_method,
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)
        return txn

    return _make


@pytest.fixture()
def make_redemption_order(db_session):
    def _make(
        user: models.User,
        txn_id: str,
        status: str = "IN_TRANSIT",
        product_name: str = "Aura Gold Coin",
        product_type: str = "coin",
        metal_type: str = "gold",
        quantity_purchased: float = 2.0,
        awb_number: str | None = "PRO19460772",
    ) -> models.RedemptionOrder:
        order = models.RedemptionOrder(
            txn_id=txn_id,
            user_id=user.id,
            product_name=product_name,
            product_type=product_type,
            metal_type=metal_type,
            quantity_purchased=quantity_purchased,
            txn_status=status,
            awb_number=awb_number,
        )
        db_session.add(order)
        db_session.commit()
        db_session.refresh(order)
        return order

    return _make


@pytest.fixture()
def flush_redis():
    from app.services.cache import get_redis

    client = get_redis()
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture()
def auth_headers():
    def _headers(user: models.User) -> dict[str, str]:
        token = create_access_token(str(user.id), user.role)
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture()
def make_conversation(db_session):
    def _make(user: models.User, title: str = "Test conversation") -> models.Conversation:
        conversation = models.Conversation(user_id=user.id, title=title)
        db_session.add(conversation)
        db_session.commit()
        db_session.refresh(conversation)
        return conversation

    return _make


@pytest.fixture()
def make_message(db_session):
    def _make(
        conversation: models.Conversation,
        role: str,
        content: str,
        response_type: str | None = None,
        response_data: dict | None = None,
        model_used: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> models.Message:
        message = models.Message(
            conversation_id=conversation.id,
            role=role,
            content=content,
            response_type=response_type,
            response_data=response_data,
            model_used=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
        db_session.add(message)
        db_session.commit()
        db_session.refresh(message)
        return message

    return _make
