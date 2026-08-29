"""Re-tests only the rows currently marked passed=False in
scripts/fixtures/real_scenario_results.csv (not the full 60-question set) -
used to check whether a targeted fix resolved specific known failures without
re-running (and re-paying for) the whole eval.

Writes the same results CSV back with each retested row's outcome updated in
place, plus a new `fixed` column: "yes" if it was False before and now
passes, "no" if it was False and still fails, blank for every row that
wasn't retested (still whatever it was before).

Run from `backend/` with the venv active and OPENAI_API_KEY set:
    python -m scripts.retest_failed_scenarios
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services.orchestrator import chat_turn  # noqa: E402
from scripts.eval_real_scenarios import RESULTS_PATH, _passes  # noqa: E402

FIELDNAMES = [
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
    "fixed",
]


def main() -> None:
    db = SessionLocal()
    try:
        alice = db.query(User).filter(User.username == "alice").first()
        if alice is None:
            print("No alice user found - run `python -m scripts.seed` first.")
            return

        with RESULTS_PATH.open(newline="") as f:
            rows = list(csv.DictReader(f))

        to_retest = [r for r in rows if r["passed"] == "False"]
        print(f"Retesting {len(to_retest)} previously-failed row(s) (out of {len(rows)} total)...\n")

        retested_ids = set()
        for row in to_retest:
            response = chat_turn(db, alice, row["question"], [], conversation_id=f"retest-{row['id']}")
            passed, reason = _passes(response, row["expected_type"], row["expected_contains"])
            retested_ids.add(row["id"])

            status = "PASS" if passed else "FAIL"
            print(f"[{status:4}] #{row['id']:>2} ({row['category']:14}) {row['question'][:70]}")
            if not passed:
                print(f"         -> {reason}")
                print(f"         -> got: {response.message[:150]}")

            row["actual_type"] = response.type.value
            row["actual_message"] = response.message
            row["passed"] = str(passed)
            row["fail_reason"] = reason
            row["fixed"] = "yes" if passed else "no"

        for row in rows:
            row.setdefault("fixed", "")

        with RESULTS_PATH.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

        fixed_count = sum(1 for r in to_retest if r["id"] in retested_ids and r["fixed"] == "yes")
        print(f"\n{fixed_count}/{len(to_retest)} previously-failing rows now pass.")
        print(f"Updated {RESULTS_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
