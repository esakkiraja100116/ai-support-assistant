"""Real-scenario eval: runs 60 realistic customer messages (single-topic FAQ,
compound FAQ, transaction-only, combined transaction+FAQ, and out-of-scope
questions) through the actual chat_turn() pipeline against alice's real
seeded data, and reports a pass/fail count against expectations in
scripts/fixtures/real_scenario_questions.csv.

Each row's `expected_contains` is a semicolon-separated list of substrings
that must ALL appear (case-insensitive) somewhere in the response message or
its structured data for a pass. `expected_type` is the ChatResponse.type
expected, with two special values:
- "TEXT_ANSWER_OR_TRANSACTION" (the `combined` category) accepts any
  non-error type, since the current architecture only ever routes to ONE
  tool per turn and so can only ever fully address one half of a combined
  transaction+FAQ question - this eval exists specifically to measure how
  often that matters, not to assert it never does.
- "TEXT_ANSWER_GROUNDED" (the `out_of_scope` category) requires a TEXT_ANSWER
  with grounded=True, confirming the turn was handled by respond_directly
  (genuine capability gap / greeting / unrelated topic) rather than an
  accidental search_knowledge_base call landing on insufficient_kb_info,
  which renders identically to the customer but is the wrong route.

This is a real, non-mocked run (actual OpenAI calls, actual cost) - not part
of pytest. Run from `backend/` with the venv active and OPENAI_API_KEY set:
    python -m scripts.eval_real_scenarios
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services import session_log  # noqa: E402
from app.services.orchestrator import chat_turn  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "real_scenario_questions.csv"
RESULTS_PATH = Path(__file__).resolve().parent / "fixtures" / "real_scenario_results.csv"


def _last_session_cost(session_id: str) -> float:
    path = session_log.LOGS_DIR / f"{session_id}.jsonl"
    if not path.exists():
        return 0.0
    last_cost = 0.0
    for line in path.open():
        event = json.loads(line)
        if "session_total_cost_usd" in event:
            last_cost = event["session_total_cost_usd"]
    return last_cost


def _passes(response, expected_type: str, expected_contains: str) -> tuple[bool, str]:
    if response.type.value == "ERROR":
        return False, "got ERROR response"

    if expected_type == "TEXT_ANSWER_GROUNDED":
        # Used for the out_of_scope category: confirms the turn went through
        # respond_directly (grounded=True) rather than an accidental
        # search_knowledge_base call that happened to come back empty
        # (insufficient_kb_info also renders as TEXT_ANSWER, but grounded=False) -
        # a wrong route that would look identical to the customer but isn't.
        if response.type.value != "TEXT_ANSWER":
            return False, f"expected TEXT_ANSWER, got {response.type.value}"
        if not (response.data or {}).get("grounded"):
            return False, "expected grounded=True (respond_directly), got grounded=False (KB path was used instead)"
    elif expected_type != "TEXT_ANSWER_OR_TRANSACTION" and response.type.value != expected_type:
        return False, f"expected type {expected_type}, got {response.type.value}"

    haystack = (response.message + " " + str(response.data or "")).lower()
    missing = [kw for kw in expected_contains.split(";") if kw.strip().lower() not in haystack]
    if missing:
        return False, f"missing: {', '.join(missing)}"

    return True, ""


def main() -> None:
    db = SessionLocal()
    try:
        alice = db.query(User).filter(User.username == "alice").first()
        if alice is None:
            print("No alice user found - run `python -m scripts.seed` first.")
            return

        with FIXTURE_PATH.open(newline="") as f:
            rows = list(csv.DictReader(f))

        results = []
        by_category: dict[str, list[bool]] = {}
        # chat_turn() opens its OWN session_log scope per call (keyed by the
        # conversation_id we pass it), which shadows any outer scope for the
        # duration of that call - so per-call cost has to be read back from
        # each call's own JSONL log after the fact, not accumulated in an
        # outer recorder here (that would silently stay at 0).
        for row in rows:
            conversation_id = f"eval-{row['id']}"
            response = chat_turn(db, alice, row["question"], [], conversation_id=conversation_id)
            passed, reason = _passes(response, row["expected_type"], row["expected_contains"])

            by_category.setdefault(row["category"], []).append(passed)
            status = "PASS" if passed else "FAIL"
            print(f"[{status:4}] #{row['id']:>2} ({row['category']:14}) {row['question'][:70]}")
            if not passed:
                print(f"         -> {reason}")
                print(f"         -> got: {response.message[:150]}")

            results.append(
                {
                    **row,
                    "actual_type": response.type.value,
                    "actual_message": response.message,
                    "passed": passed,
                    "fail_reason": reason,
                }
            )

        total_cost = sum(_last_session_cost(f"eval-{row['id']}") for row in rows)

        with RESULTS_PATH.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "id",
                    "category",
                    "question",
                    "expected_type",
                    "expected_contains",
                    "notes",
                    "actual_type",
                    "actual_message",
                    "passed",
                    "fail_reason",
                ],
            )
            writer.writeheader()
            writer.writerows(results)

        total_passed = sum(1 for r in results if r["passed"])
        print(f"\n{total_passed}/{len(results)} passed overall")
        for category, outcomes in by_category.items():
            print(f"  {category:14} {sum(outcomes)}/{len(outcomes)}")
        print(f"\nSession cost: ${total_cost:.4f}")
        print(f"Full results written to {RESULTS_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
