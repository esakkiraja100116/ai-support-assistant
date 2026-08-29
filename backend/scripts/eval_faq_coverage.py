"""Runs the full 180-question fixture (scripts/fixtures/faq_variations.json)
through the real POST /chat pipeline (orchestrator.chat_turn - the exact same
function the API uses, not a shortcut) and reports how many were correctly
answered from the knowledge base vs declined vs errored vs misrouted.

This intentionally does NOT change any retrieval/prompt code to make numbers
look better - it's a read-only report against the current architecture as-is,
run by hand when you want to check retrieval health after a change:

    python -m scripts.eval_faq_coverage
    python -m scripts.eval_faq_coverage --limit 10                      # quick cost check
    python -m scripts.eval_faq_coverage --judgment-model gpt-5.6-sol --judgment-reasoning-effort none

Every question's full turn (user message, tool calls, final answer, cost) is
appended to logs/<session_id>.jsonl via the same session logging every real
chat request goes through - see app/services/session_log.py.
"""
import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judgment-model", default=None, help="Override the model for the KB judgment call only")
    parser.add_argument("--judgment-reasoning-effort", default=None, help="e.g. 'none' - required by some reasoning models to allow tool calls")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N questions (across all FAQs) - for a quick cost check before a full run")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not FIXTURE_PATH.exists():
        print(f"{FIXTURE_PATH} not found - run `python -m scripts.generate_faq_variations` first.")
        return

    fixture = json.loads(FIXTURE_PATH.read_text())

    flat_questions = [(item["faq_id"], item["original_question"], v) for item in fixture for v in item["variations"]]
    if args.limit:
        flat_questions = flat_questions[: args.limit]
    total_questions = len(flat_questions)

    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.username).first()
        if user is None:
            print("No seeded users found - run `python -m scripts.seed` first.")
            return

        session_id = f"eval-faq-coverage-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        label = f" (judgment_model={args.judgment_model}, reasoning_effort={args.judgment_reasoning_effort})" if args.judgment_model else ""
        print(f"Running {total_questions} question(s) as session {session_id!r}{label}...\n")

        per_faq_counts: dict[int, dict] = {}
        overall_counts = {"answered": 0, "declined": 0, "error": 0, "misrouted": 0}

        for faq_id, original_question, question in flat_questions:
            try:
                response = chat_turn(
                    db, user, question, [],
                    conversation_id=session_id,
                    judgment_model=args.judgment_model,
                    judgment_reasoning_effort=args.judgment_reasoning_effort,
                )
                outcome = classify(response)
            except Exception as exc:
                outcome = "error"
                print(f"  ! exception on {question!r}: {exc}")
            overall_counts[outcome] += 1
            bucket = per_faq_counts.setdefault(faq_id, {"question": original_question, "total": 0, "answered": 0})
            bucket["total"] += 1
            if outcome == "answered":
                bucket["answered"] += 1

        for faq_id, bucket in per_faq_counts.items():
            print(f"[{faq_id:>2}] {bucket['question']:<50} {bucket['answered']:>2}/{bucket['total']} covered")

        total_cost = 0.0
        with session_log.session_scope(session_id) as recorder:
            total_cost = recorder.total_cost_usd

        print("\n" + "=" * 70)
        print(f"TOTAL: {overall_counts['answered']}/{total_questions} answered from the knowledge base")
        print(f"       {overall_counts['declined']}/{total_questions} declined (\"I don't have enough information\")")
        print(f"       {overall_counts['error']}/{total_questions} errored")
        print(f"       {overall_counts['misrouted']}/{total_questions} misrouted to the transaction path")
        print(f"Session cost: ${total_cost:.4f}  (full detail: backend/logs/{session_id}.jsonl)")
        if total_questions:
            print(f"Avg cost/question: ${total_cost / total_questions:.5f}  (x180 projected: ${total_cost / total_questions * 180:.4f})")
        print("=" * 70)

        with session_log.session_scope(session_id) as recorder:
            recorder.log(
                "eval_summary",
                total_questions=total_questions,
                counts=overall_counts,
                total_cost_usd=round(total_cost, 6),
                judgment_model=args.judgment_model,
                judgment_reasoning_effort=args.judgment_reasoning_effort,
                per_faq=[
                    {"faq_id": fid, "question": b["question"], "covered": b["answered"], "total": b["total"]}
                    for fid, b in per_faq_counts.items()
                ],
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
