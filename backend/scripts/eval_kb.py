"""Manual retrieval eval: prints similarity scores for a fixed set of test
queries against the seeded knowledge base, comparing the raw query against
what the intent-routing model rephrases it into. Not part of the pytest
suite (it makes real OpenAI calls) - run by hand when tuning retrieval:

    python -m scripts.eval_kb
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import kb_service, llm_client  # noqa: E402
from app.services.tools_schema import ALL_TOOLS, SYSTEM_PROMPT  # noqa: E402

TEST_QUERIES = [
    # Should match "How do I sell my gold?"
    "How do I sell my gold?",
    "How can I exchange my gold for cash?",
    "How do I cash out my gold?",
    "Can I liquidate my gold holdings?",
    "How do I turn my gold into money?",
    "What is the process to sell gold?",
    # Should match other seeded FAQs
    "How does recurring savings work?",
    "What documents do I need for KYC?",
    "Is my gold insured against theft?",
    # Should NOT match anything (out of scope / no seeded answer)
    "What is the capital of France?",
    "Do you support international wire transfers?",
]


def rephrased_query(raw_query: str) -> str | None:
    """Mimics the real intent-routing call to see what the model would
    actually search for, since the live /chat path lets it rephrase."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": raw_query},
    ]
    msg = llm_client.chat_completion(messages, tools=ALL_TOOLS, tool_choice="auto")
    for call in msg.tool_calls or []:
        if call.function.name == "search_knowledge_base":
            import json

            return json.loads(call.function.arguments or "{}").get("query")
    return None


def main() -> None:
    db = SessionLocal()
    print(f"{'query':<45} {'raw score':>10} {'rephrased':<35} {'rephr. score':>12}  top match")
    print("-" * 130)
    for query in TEST_QUERIES:
        raw = kb_service.search_knowledge_base(db, query)
        rq = rephrased_query(query)
        rq_score = kb_service.search_knowledge_base(db, rq).best_similarity if rq else None
        top = raw.articles[0].question if raw.articles else "-"
        print(
            f"{query!r:<45} {raw.best_similarity:>10.3f} {rq!r:<35} "
            f"{f'{rq_score:.3f}' if rq_score is not None else '-':>12}  {top}"
        )
    db.close()


if __name__ == "__main__":
    main()
