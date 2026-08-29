"""Generates 10 alternative customer phrasings for each seeded FAQ question,
producing a fixed 18x10 = 180-question test fixture for scripts/eval_faq_coverage.py.

This is a one-time (or re-run-when-you-want-a-fresh-set) generation step, not
something run automatically before every eval - the output is a committed,
reviewable fixture (scripts/fixtures/faq_variations.json), not a moving target.

Run from `backend/` with the venv active and OPENAI_API_KEY set:
    python -m scripts.generate_faq_variations
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import SupportArticle  # noqa: E402
from app.services import llm_client  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "fixtures" / "faq_variations.json"

GENERATE_PROMPT = (
    "You are helping build a test set for a customer support chatbot for a platform "
    "where customers buy and sell gold (only gold - GOLD24/GOLD22 - not silver or any "
    "other metal). Given one approved FAQ question and its answer, write exactly 10 "
    "alternative ways a real customer might ask the SAME underlying question - vary "
    "phrasing, formality, directness, and word choice (synonyms, indirect phrasing, "
    "casual tone, etc). Do not mention silver or any product this platform doesn't "
    "offer. Do not change what is being asked. Return ONLY a JSON array of 10 strings, "
    "no other text.\n\n"
    "FAQ question: {question}\n"
    "FAQ answer: {answer}"
)


def generate_variations(question: str, answer: str) -> list[str]:
    response = llm_client.chat_completion(
        [{"role": "user", "content": GENERATE_PROMPT.format(question=question, answer=answer)}]
    )
    content = (response.content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    variations = json.loads(content)
    if not isinstance(variations, list) or len(variations) < 1:
        raise ValueError(f"Unexpected response shape for {question!r}: {content!r}")
    return variations[:10]


def main() -> None:
    db = SessionLocal()
    try:
        articles = db.query(SupportArticle).order_by(SupportArticle.id).all()
        if not articles:
            print("No FAQ articles found - run `python -m scripts.seed` first.")
            return

        fixture = []
        for article in articles:
            print(f"Generating variations for [{article.id}] {article.question!r}...")
            variations = generate_variations(article.question, article.answer)
            fixture.append(
                {
                    "faq_id": article.id,
                    "original_question": article.question,
                    "variations": variations,
                }
            )

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_PATH.open("w") as f:
            json.dump(fixture, f, indent=2)

        total = sum(len(item["variations"]) for item in fixture)
        print(f"\nWrote {len(fixture)} FAQs x ~10 variations = {total} questions to {OUTPUT_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
