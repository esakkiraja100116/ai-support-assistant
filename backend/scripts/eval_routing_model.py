"""One-off controlled experiment: re-runs known intent-routing failures using
a different model for JUST the top-level routing decision, via
orchestrator._route_intent's model override. Isolates whether a stronger
model's judgment alone fixes these further, on top of the tool_choice
="required" change already adopted in _route_intent (see orchestrator.py's
docstring there for the measured before/after on that change).

All 5 are real routing misses found via manual testing against gpt-4o-mini
with tool_choice="auto" (the original behavior): each has either a strong KB
match (confirmed via kb_service directly - similarity 0.6-0.86) or is a
directly answerable transaction question, yet the router either declined as
small-talk or (worse, for "when that status will get update ?") fabricated an
ungrounded answer without calling any tool at all.

This is a targeted regression comparison, not a general eval - it exists to
answer one question (does model X route these specific known-hard cases
correctly?), not to replace manual/live testing of the full app. Not part of
pytest.

Run from `backend/` with the venv active and OPENAI_API_KEY set:
    python -m scripts.eval_routing_model gpt-4o-mini
    python -m scripts.eval_routing_model gpt-5.6-sol none
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.schemas.chat import ChatMessage  # noqa: E402
from app.services import orchestrator, session_log  # noqa: E402

KNOWN_ROUTING_FAILURES: list[tuple[str, list[ChatMessage], str]] = [
    ("Where do you get your live gold rates from?", [], "search_knowledge_base"),
    ("Why does the gold price change every day?", [], "search_knowledge_base"),
    ("What factors affect today's gold price?", [], "search_knowledge_base"),
    ("Total how many success transaction ?", [], "get_recent_transactions"),
    (
        "when that status will get update ?",
        [
            ChatMessage(role="user", content="What can you tell me about transaction txn_1005?"),
            ChatMessage(
                role="assistant",
                content=(
                    'Hi Alice! I see that you\'ve initiated a transaction to buy GOLD22 for an '
                    'amount of 3200.0. Currently, this transaction is in a "PENDING" status.'
                ),
            ),
        ],
        "search_knowledge_base",
    ),
]


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Usage: python -m scripts.eval_routing_model <model-name> [reasoning_effort]")
        return
    model = sys.argv[1]
    reasoning_effort = sys.argv[2] if len(sys.argv) == 3 else None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "alice").first()
        if user is None:
            print("No alice user found - run `python -m scripts.seed` first.")
            return

        session_id = f"routing-model-test-{model}"
        resolved = 0
        with session_log.session_scope(session_id) as recorder:
            for question, history, expected_tool in KNOWN_ROUTING_FAILURES:
                try:
                    assistant_message = orchestrator._route_intent(
                        user, question, history, model=model, reasoning_effort=reasoning_effort
                    )
                except Exception as exc:
                    print(f"[{'API ERROR':45}] {question}  ({exc})")
                    continue

                tool_calls = getattr(assistant_message, "tool_calls", None) or []
                called = tool_calls[0].function.name if tool_calls else None
                correct = called == expected_tool
                if correct:
                    resolved += 1
                status = "FIXED" if correct else f"WRONG (called {called or 'nothing - answered directly'})"
                print(f"[{status:45}] {question}")
                if called == "respond_directly":
                    import json

                    args_json = json.loads(tool_calls[0].function.arguments or "{}")
                    print(f"           -> {args_json.get('reply', '')[:160]}")
                elif not tool_calls and assistant_message.content:
                    print(f"           -> {assistant_message.content[:160]}")

            total = len(KNOWN_ROUTING_FAILURES)
            suffix = f" (reasoning_effort={reasoning_effort})" if reasoning_effort else ""
            print(f"\n{resolved}/{total} known routing failures fixed by {model}{suffix}")
            print(f"Session cost: ${recorder.total_cost_usd:.4f} (0 if {model} isn't in pricing.py's table)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
