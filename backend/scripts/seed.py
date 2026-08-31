"""Idempotent seed script: resets synthetic demo data (transactions,
redemption orders, support articles) and upserts the fixed demo users, but
deliberately never touches `conversations`/`messages` - that's real usage
history (actual chat turns, whether from manual testing or real traffic),
not demo data, and re-running this script should never destroy it.

Users are upserted by username (found-or-created, existing id preserved)
rather than dropped and recreated, specifically so `conversations.user_id`
foreign keys never dangle and existing conversation history stays valid
across repeated runs.

Run from the `backend/` directory with the venv active and OPENAI_API_KEY set:
    python -m scripts.seed
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import SupportArticle, Transaction, User  # noqa: E402
from app.services import llm_client  # noqa: E402

USERS = [
    {"username": "alice", "display_name": "Alice Nguyen", "role": "USER"},
    {"username": "bob", "display_name": "Bob Fernandez", "role": "USER"},
    # carol/dave/erin exist specifically to make the redemption-tracking
    # minimum test matrix's DB-state rows testable as real conversations,
    # not just automated fixtures - bob already covers "no redemptions" (T1),
    # alice already covers "multiple ongoing" (T5); these three fill the
    # states neither of them has: delivered-only (T2), failed-only (T3), and
    # exactly-one-ongoing (T4).
    {"username": "carol", "display_name": "Carol Mensah", "role": "USER"},
    {"username": "dave", "display_name": "Dave Okafor", "role": "USER"},
    {"username": "erin", "display_name": "Erin Walsh", "role": "USER"},
    # frank covers T7: ongoing + delivered + failed all at once, on one user,
    # so "only ongoing is considered" is testable against every exclusion
    # category simultaneously, not just one at a time.
    {"username": "frank", "display_name": "Frank Torres", "role": "USER"},
    {"username": "admin", "display_name": "Amara Singh (Admin)", "role": "ADMINISTRATOR"},
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

# Alice's redemptions, cross-referenced to the AWBs in
# app/services/tracking_fixtures.py so the demo chat flow ("where is my
# order") has real ongoing orders to resolve/track against - 4 ongoing
# (one per fixture AWB, plus one with no AWB yet) + 1 already-delivered
# (excluded from active discovery, per the spec's own note - reachable only
# via a direct tracking_service call, not through chat). Each is a
# Transaction row with type=REDEMPTION, linked via related_transaction_id to
# a SUCCESS-status BUY transaction - a redemption only ever happens because
# gold was actually bought first, so this is a real, meaningful relationship
# rather than a free-text label. carol/dave/erin (see EXTRA_REDEMPTIONS
# below) get the same treatment for the DB states alice/bob don't cover.
REDEMPTION_TEMPLATES = [
    {"product": "Gold Bar", "product_type": "bar", "metal_type": "gold",
     "quantity": 5.0, "status": "DELIVERED", "awb_number": "PRO19460771"},
    {"product": "Gold Coin", "product_type": "coin", "metal_type": "gold",
     "quantity": 2.0, "status": "IN_TRANSIT", "awb_number": "PRO19460772"},
    {"product": "Gold Bar", "product_type": "bar", "metal_type": "gold",
     "quantity": 1.0, "status": "OUT_FOR_DELIVERY", "awb_number": "PRO19460773"},
    {"product": "Gold Coin", "product_type": "coin", "metal_type": "gold",
     "quantity": 3.0, "status": "ATTEMPTED", "awb_number": "PRO19460774"},
    {"product": "Gold Bar", "product_type": "bar", "metal_type": "gold",
     "quantity": 10.0, "status": "PROCESSING", "awb_number": None},
]

# One redemption each for carol/dave/erin - see the USERS list comment for
# why these three exist. Each list holds exactly one row, kept in the same
# dict-of-templates shape as REDEMPTION_TEMPLATES so the seeding loop below
# can treat alice and these three uniformly.
EXTRA_REDEMPTIONS: dict[str, list[dict]] = {
    # T2: delivered only - zero ongoing orders, never reachable via the
    # tracking flow at all (no fixture needed for its AWB).
    "carol": [
        {"product": "Gold Bar", "product_type": "bar", "metal_type": "gold",
         "quantity": 6.0, "status": "DELIVERED", "awb_number": "PRO19460781"},
    ],
    # T3: failed/cancelled only - zero ongoing orders, same reasoning.
    "dave": [
        {"product": "Gold Coin", "product_type": "coin", "metal_type": "gold",
         "quantity": 4.0, "status": "CANCELLED", "awb_number": "PRO19460782"},
    ],
    # T4: exactly one ongoing order with a real AWB - auto-selects straight
    # to tracking, no selector step. Uses its own fixture (PRO19460780 in
    # tracking_fixtures.py) rather than reusing one of alice's.
    "erin": [
        {"product": "Gold Bar", "product_type": "bar", "metal_type": "gold",
         "quantity": 4.0, "status": "IN_TRANSIT", "awb_number": "PRO19460780"},
    ],
    # T7: one ongoing (with a real AWB, PRO19460783) alongside one delivered
    # and one failed - "only the ongoing order is considered" tested against
    # all three categories on a single user at once.
    "frank": [
        {"product": "Gold Bar", "product_type": "bar", "metal_type": "gold",
         "quantity": 3.0, "status": "DELIVERED", "awb_number": "PRO19460784"},
        {"product": "Gold Coin", "product_type": "coin", "metal_type": "gold",
         "quantity": 2.0, "status": "IN_TRANSIT", "awb_number": "PRO19460783"},
        {"product": "Gold Coin", "product_type": "coin", "metal_type": "gold",
         "quantity": 1.0, "status": "REJECTED", "awb_number": "PRO19460785"},
    ],
}


def seed() -> None:
    db = SessionLocal()
    try:
        # Only synthetic demo data is reset here - never messages/conversations
        # (real usage history) or users (would orphan/cascade-delete that
        # history via the conversations.user_id foreign key). transactions
        # isn't referenced by any other table, so truncating it can't cascade
        # into anything else.
        db.execute(text("TRUNCATE TABLE transactions, support_articles RESTART IDENTITY CASCADE"))
        db.commit()

        users = {}
        for spec in USERS:
            user = db.scalars(select(User).where(User.username == spec["username"])).first()
            if user is None:
                user = User(username=spec["username"], display_name=spec["display_name"], role=spec["role"])
                db.add(user)
            else:
                user.display_name = spec["display_name"]
                user.role = spec["role"]
            users[spec["username"]] = user
        db.flush()

        txn_seq = 1001
        now = datetime.now(timezone.utc)
        successful_buy_id_by_username: dict[str, str] = {}
        for username, user in users.items():
            if user.role == "ADMINISTRATOR":
                continue
            for i, tpl in enumerate(TXN_TEMPLATES):
                created = now - timedelta(days=len(TXN_TEMPLATES) - i)
                txn_id = f"txn_{txn_seq}"
                db.add(
                    Transaction(
                        id=txn_id,
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
                if username not in successful_buy_id_by_username and tpl["type"] == "BUY" and tpl["status"] == "SUCCESS":
                    successful_buy_id_by_username[username] = txn_id
                txn_seq += 1

        redemptions_by_username = {"alice": REDEMPTION_TEMPLATES, **EXTRA_REDEMPTIONS}
        rdm_seq = 1
        for username, templates in redemptions_by_username.items():
            user = users.get(username)
            if user is None:
                continue
            for i, tpl in enumerate(templates):
                created = now - timedelta(days=len(templates) - i)
                db.add(
                    Transaction(
                        id=f"rdm_{rdm_seq:04d}",
                        user_id=user.id,
                        type="REDEMPTION",
                        product=tpl["product"],
                        amount=None,
                        status=tpl["status"],
                        failure_reason=None,
                        payment_method=None,
                        awb_number=tpl["awb_number"],
                        product_type=tpl["product_type"],
                        metal_type=tpl["metal_type"],
                        quantity=tpl["quantity"],
                        related_transaction_id=successful_buy_id_by_username.get(username),
                        created_at=created,
                        updated_at=created,
                    )
                )
                rdm_seq += 1

        # Committed before embedding starts: users/transactions require no
        # external API and should land even if OPENAI_API_KEY is missing or
        # invalid, rather than being rolled back by a later embedding failure.
        db.commit()

        print(f"Embedding {len(FAQS)} support articles...")
        for question, answer, category in FAQS:
            # Embed the question only: incoming queries are phrased as questions,
            # so question-to-question similarity is a much cleaner retrieval signal
            # than diluting the vector with answer text.
            embedding = llm_client.embed(question)
            db.add(SupportArticle(question=question, answer=answer, category=category, tags=[category], embedding=embedding))

        db.commit()
        txn_count = sum(1 for u in users.values() if u.role != "ADMINISTRATOR") * len(TXN_TEMPLATES)
        redemption_count = rdm_seq - 1
        print(
            f"Seeded {len(users)} users, {txn_count} transactions, "
            f"{redemption_count} redemption orders, {len(FAQS)} support articles."
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
