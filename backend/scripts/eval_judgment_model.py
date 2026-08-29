"""One-off controlled experiment: re-runs the exact 16 questions that failed at the
answer_from_kb/insufficient_kb_info judgment step (from the 2026-08-29 eval run - see
docs/faq-coverage-testing.md) using a different model for JUST that judgment call,
via `_handle_knowledge_base`'s `judgment_model` override. Retrieval is unchanged and
already known to succeed for all of these (verified by hand before writing this list) -
this isolates whether a different model's judgment alone would resolve them.

This is a targeted regression comparison, not a general eval - it exists to answer
one question (does model X judge these specific known-hard cases better?) before
deciding whether to adopt a different judgment model generally. Not part of pytest.

Run from `backend/` with the venv active and OPENAI_API_KEY set:
    python -m scripts.eval_judgment_model gpt-5.6-sol
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services import orchestrator, session_log  # noqa: E402

# (question, expected source FAQ id) - all confirmed retrieved as candidates already,
# so any decline here is purely a judgment call, not a retrieval miss.
KNOWN_JUDGMENT_FAILURES = [
    ("Can I sell multiple products at once?", 1),
    ("What payment methods are available for gold transactions on your platform?", 2),
    ("What payment methods can I use for the recurring gold buying schedule?", 3),
    ("Is any additional documentation required beyond the photo ID and proof of address?", 4),
    ("Do payouts happen on weekends or only during business days?", 6),
    ("How frequently are the vaults audited for the gold I own?", 9),
    ("What do I need to do to access Recurring Plans in my account settings?", 10),
    ("Is there a restriction on how much gold I can sell after I meet the minimum investment?", 11),
    ("If I invest the minimum amount, can I still fully utilize the platform's services?", 11),
    ("Is there any additional information I need to provide when changing my bank account?", 13),
    ("Can gold be shipped to an address that isn't verified?", 14),
    ("What happens if I don't use the reset link in time?", 16),
    ("Are there any hidden fees for resetting my password?", 16),
    ("How do I find the 'Talk to an agent' option in the Help menu?", 18),
    ("During what hours is the human support team available?", 18),
    ("Is it guaranteed that I will be able to talk to a human if I click on the agent option?", 18),
]


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Usage: python -m scripts.eval_judgment_model <model-name> [reasoning_effort]")
        return
    model = sys.argv[1]
    reasoning_effort = sys.argv[2] if len(sys.argv) == 3 else None

    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.username).first()
        if user is None:
            print("No seeded users found - run `python -m scripts.seed` first.")
            return

        session_id = f"judgment-model-test-{model}"
        resolved_count = 0
        error_count = 0
        with session_log.session_scope(session_id) as recorder:
            for question, expected_faq_id in KNOWN_JUDGMENT_FAILURES:
                response = orchestrator._handle_knowledge_base(
                    db, user, question, judgment_model=model, judgment_reasoning_effort=reasoning_effort
                )
                if response.type.value == "ERROR":
                    error_count += 1
                    print(f"[{'API ERROR':24}] {question}")
                    continue
                grounded = (response.data or {}).get("grounded")
                sources = (response.data or {}).get("sources", [])
                correct = grounded is True and expected_faq_id in sources
                if correct:
                    resolved_count += 1
                status = "FIXED" if correct else ("ANSWERED (wrong source)" if grounded else "still declined")
                print(f"[{status:24}] {question}")

            total = len(KNOWN_JUDGMENT_FAILURES)
            print(f"\n{resolved_count}/{total} of the known judgment failures resolved by {model}"
                  f"{f' (reasoning_effort={reasoning_effort})' if reasoning_effort else ''}")
            if error_count:
                print(f"WARNING: {error_count}/{total} calls errored (see traceback above) - "
                      f"results above are NOT a real measurement, fix the API call first.")
            print(f"Session cost: ${recorder.total_cost_usd:.4f} (0 if {model} isn't in pricing.py's table)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
