"""Idempotent seed script: truncates and re-inserts users, transactions, and
support articles (embedding each article via the OpenAI embeddings API).

Run from the `backend/` directory with the venv active and OPENAI_API_KEY set:
    python -m scripts.seed
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import SupportArticle, Transaction, User  # noqa: E402
from app.services import llm_client  # noqa: E402

USERS = [
    {"username": "alice", "display_name": "Alice Nguyen"},
    {"username": "bob", "display_name": "Bob Fernandez"},
]

FAQS = [
    ("How do I sell my gold?", "Open the app, go to Portfolio > Sell, choose the product and quantity, and confirm at the live market rate. Funds are credited to your linked bank account after settlement.", "trading"),
    ("How do I buy gold?", "Go to Buy on the home screen, choose GOLD24 or GOLD22, enter an amount or grams, and pay via UPI, card, or net banking. Your holdings update once payment is confirmed.", "trading"),
    ("How does recurring savings work?", "A recurring (systematic) savings plan automatically buys a fixed amount of gold on a schedule you choose (weekly or monthly) from your saved payment method, helping you average your purchase price over time.", "recurring"),
    ("What KYC documents do I need?", "We require a government photo ID (passport, driver's license, or national ID) and a proof of address dated within the last 3 months to complete KYC verification.", "account"),
    ("Why might a transaction fail?", "Transactions commonly fail due to insufficient funds, a declined card, bank server timeouts, or KYC verification not yet being complete. Check the failure reason shown on the transaction for specifics.", "trading"),
    ("How long do payouts take?", "Payouts to your linked bank account are typically processed within 1-2 business days after a sell order settles.", "payments"),
    ("What fees do you charge?", "We charge a small spread on buy/sell orders (typically 0.5%-1%) plus applicable payment processing fees; there are no separate account maintenance fees.", "fees"),
    ("What does 24K vs 22K gold mean?", "24K (GOLD24) is 99.9% pure gold, while 22K (GOLD22) is about 91.6% pure and alloyed with other metals for durability. Purity affects price per gram.", "products"),
    ("How is my gold stored?", "Gold purchased through the platform is held in insured, audited vaults on your behalf; you own the underlying metal and can request delivery or sell at any time.", "products"),
    ("How do I cancel a recurring savings plan?", "Go to Recurring Plans in your account settings, select the active plan, and choose Cancel. Any already-purchased gold remains in your portfolio.", "recurring"),
    ("What is the minimum investment amount?", "You can start investing with as little as the equivalent of 100 in your local currency; there is no maximum limit beyond standard KYC-based transaction thresholds.", "trading"),
    ("Do you have a referral program?", "Yes - share your referral code from the Rewards tab; both you and your friend receive bonus gold credit once they complete their first purchase.", "rewards"),
    ("How do I update my bank account for payouts?", "Go to Settings > Payment Methods > Bank Accounts, add the new account, and verify it with a small test deposit before setting it as your default payout account.", "account"),
    ("Can I take physical delivery of my gold?", "Yes, eligible holdings above the minimum delivery threshold can be redeemed as physical gold coins or bars, shipped securely to your verified address for a delivery fee.", "products"),
    ("What happens if I place an order when markets are closed?", "Orders placed outside trading hours are queued and executed at the next available live market rate once trading resumes.", "trading"),
    ("How do I reset my account password?", "Use the 'Forgot password' link on the login screen to receive a reset link by email; for security this link expires after 30 minutes.", "account"),
    ("Is my investment insured?", "Gold held in our vaults is covered by comprehensive insurance against theft and physical loss; this does not cover market price fluctuations.", "products"),
    ("How do I contact human customer support?", "If the assistant can't resolve your question, use the 'Talk to an agent' option in the Help menu to reach our human support team during business hours.", "account"),
]

TXN_TEMPLATES = [
    {"type": "BUY", "product": "GOLD24", "amount": 5000, "status": "FAILED", "failure_reason": "Payment gateway declined the card", "payment_method": "Credit Card"},
    {"type": "BUY", "product": "GOLD24", "amount": 2500, "status": "SUCCESS", "failure_reason": None, "payment_method": "UPI"},
    {"type": "SELL", "product": "GOLD22", "amount": 1800, "status": "SUCCESS", "failure_reason": None, "payment_method": "Net Banking"},
    {"type": "RECURRING_BUY", "product": "GOLD24", "amount": 1000, "status": "SUCCESS", "failure_reason": None, "payment_method": "UPI"},
    {"type": "BUY", "product": "GOLD22", "amount": 3200, "status": "PENDING", "failure_reason": None, "payment_method": "Net Banking"},
    {"type": "SELL", "product": "GOLD24", "amount": 4100, "status": "REFUNDED", "failure_reason": "Order cancelled after settlement delay", "payment_method": "Wallet"},
    {"type": "RECURRING_BUY", "product": "GOLD22", "amount": 1000, "status": "FAILED", "failure_reason": "Insufficient funds in linked account", "payment_method": "Net Banking"},
]


def seed() -> None:
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE TABLE transactions, users, support_articles RESTART IDENTITY CASCADE"))
        db.commit()

        users = {}
        for spec in USERS:
            user = User(id=uuid.uuid4(), username=spec["username"], display_name=spec["display_name"])
            db.add(user)
            users[spec["username"]] = user
        db.flush()

        txn_seq = 1001
        now = datetime.now(timezone.utc)
        for username, user in users.items():
            for i, tpl in enumerate(TXN_TEMPLATES):
                created = now - timedelta(days=len(TXN_TEMPLATES) - i)
                db.add(
                    Transaction(
                        id=f"txn_{txn_seq}",
                        user_id=user.id,
                        type=tpl["type"],
                        product=tpl["product"],
                        amount=tpl["amount"],
                        status=tpl["status"],
                        failure_reason=tpl["failure_reason"],
                        payment_method=tpl["payment_method"],
                        created_at=created,
                        updated_at=created,
                    )
                )
                txn_seq += 1

        print(f"Embedding {len(FAQS)} support articles...")
        for question, answer, category in FAQS:
            # Embed the question only: incoming queries are phrased as questions,
            # so question-to-question similarity is a much cleaner retrieval signal
            # than diluting the vector with answer text.
            embedding = llm_client.embed(question)
            db.add(SupportArticle(question=question, answer=answer, category=category, tags=[category], embedding=embedding))

        db.commit()
        print(f"Seeded {len(users)} users, {len(users) * len(TXN_TEMPLATES)} transactions, {len(FAQS)} support articles.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
