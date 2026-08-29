"""Replays Scenario A's 7 messages through the REAL, running backend (real
OpenAI calls, real routing, real persistence) as alice, all in one
conversation - so the actual behavior can be compared in the UI against the
golden/expected behavior documented in
scripts/generate_transaction_routing_finetune.py.

Requires the backend to already be running (e.g. `uvicorn app.main:app
--reload`) and pointed at a real OPENAI_API_KEY - this makes real API calls
and will show whatever the app actually does today, bugs included.

Run from the `backend/` directory:
    python -m scripts.replay_scenario_a
"""
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import Conversation  # noqa: E402

API_BASE_URL = "http://localhost:8000"
TITLE = "exp-1 (Scenario A)"

MESSAGES = [
    "How is the price of gold set on your platform?",
    "show me the transaction list",
    "why my last transaction was failed ?",
    "How about my first transation ?",
    "Total how many success transaction ?",
    "Is there any pending transaction ?",
    "Thanks, that's everything I needed.",
]


def main() -> None:
    conversation_id = str(uuid.uuid4())

    with httpx.Client(base_url=API_BASE_URL, timeout=60) as client:
        login = client.post("/auth/login", json={"username": "alice"})
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        for i, message in enumerate(MESSAGES, start=1):
            resp = client.post(
                "/chat",
                json={"message": message, "conversation_id": conversation_id},
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()
            print(f"[{i}] USER: {message}")
            print(f"    -> type={body['type']}  message={body['message'][:160]}")
            time.sleep(0.3)  # be gentle on rate limits between real API calls

    # Rename from its auto-generated title to something identifiable - a
    # benign metadata-only edit, doesn't touch any turn's actual content.
    db = SessionLocal()
    conversation = db.get(Conversation, uuid.UUID(conversation_id))
    conversation.title = TITLE
    db.commit()
    db.close()

    print(f"\nDone. Conversation {conversation_id} titled '{TITLE}'.")
    print(f"View as alice at http://localhost:3000/?c={conversation_id}")
    print(f"Or as admin at http://localhost:3000/admin/conversations/{conversation_id}")


if __name__ == "__main__":
    main()
