"""Runs the full 180-question fixture (scripts/fixtures/faq_variations.json)
through the real POST /chat pipeline (orchestrator.chat_turn - the exact same
function the API uses, not a shortcut) and reports how many were correctly
answered from the knowledge base vs declined vs errored vs misrouted.

This intentionally does NOT change any retrieval/prompt code to make numbers
look better - it's a read-only report against the current architecture as-is,
run by hand when you want to check retrieval health after a change:

    python -m scripts.eval_faq_coverage

Every question's full turn (user message, tool calls, final answer, cost) is
appended to logs/<session_id>.jsonl via the same session logging every real
chat request goes through - see app/services/session_log.py.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services import session_log  # noqa: E402
from app.services.orchestrator import chat_turn  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "faq_variations.json"


def classify(response) -> str:
    if response.type.value == "ERROR":
        return "error"
    if response.type.value == "TEXT_ANSWER":
        grounded = (response.data or {}).get("grounded")
        return "answered" if grounded else "declined"
    return "misrouted"  # e.g. a general FAQ question somehow triggered the transaction path


def main() -> None:
    if not FIXTURE_PATH.exists():
        print(f"{FIXTURE_PATH} not found - run `python -m scripts.generate_faq_variations` first.")
        return

    fixture = json.loads(FIXTURE_PATH.read_text())
    total_questions = sum(len(item["variations"]) for item in fixture)

    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.username).first()
        if user is None:
            print("No seeded users found - run `python -m scripts.seed` first.")
            return

        session_id = f"eval-faq-coverage-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        print(f"Running {total_questions} questions across {len(fixture)} FAQs as session {session_id!r}...\n")

        per_faq_results = []
        overall_counts = {"answered": 0, "declined": 0, "error": 0, "misrouted": 0}

        for item in fixture:
            counts = {"answered": 0, "declined": 0, "error": 0, "misrouted": 0}
            for question in item["variations"]:
                try:
                    response = chat_turn(db, user, question, [], conversation_id=session_id)
                    outcome = classify(response)
                except Exception as exc:
                    outcome = "error"
                    print(f"  ! exception on {question!r}: {exc}")
                counts[outcome] += 1
                overall_counts[outcome] += 1

            per_faq_results.append((item["faq_id"], item["original_question"], counts))
            covered = counts["answered"]
            print(f"[{item['faq_id']:>2}] {item['original_question']:<50} {covered:>2}/{len(item['variations'])} covered")

        total_cost = 0.0
        with session_log.session_scope(session_id) as recorder:
            total_cost = recorder.total_cost_usd

        print("\n" + "=" * 70)
        print(f"TOTAL: {overall_counts['answered']}/{total_questions} answered from the knowledge base")
        print(f"       {overall_counts['declined']}/{total_questions} declined (\"I don't have enough information\")")
        print(f"       {overall_counts['error']}/{total_questions} errored")
        print(f"       {overall_counts['misrouted']}/{total_questions} misrouted to the transaction path")
        print(f"Session cost: ${total_cost:.4f}  (full detail: backend/logs/{session_id}.jsonl)")
        print("=" * 70)

        with session_log.session_scope(session_id) as recorder:
            recorder.log(
                "eval_summary",
                total_questions=total_questions,
                counts=overall_counts,
                total_cost_usd=round(total_cost, 6),
                per_faq=[
                    {"faq_id": fid, "question": q, "covered": c["answered"], "total": sum(c.values())}
                    for fid, q, c in per_faq_results
                ],
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
