"""Generates 10 realistic customer questions for each seeded FAQ, producing a fixed
18x10 = 180-question test fixture for scripts/eval_faq_coverage.py.

Variations are generated from BOTH the question and the answer - not just paraphrases
of the question - since real customers ask about specific details only stated in the
answer (e.g. "why is the fee 0.5%-1%?") or ask something that requires one small
inference from the answer's content (e.g. "how many gold options are there?" from an
answer that names two specific products without stating a count). Testing on
question-only paraphrases undersells how questions actually get asked.

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
    "questions a real customer might ask that this FAQ should be able to answer. Mix "
    "three styles across the 10, roughly evenly:\n"
    "1. Paraphrases of the question itself - vary phrasing, formality, and word choice.\n"
    "2. Questions that reference a specific fact, number, or detail mentioned ONLY in "
    "the answer, not the question - e.g. if the answer states a percentage or a named "
    "option, ask about that detail directly.\n"
    "3. Questions that require one small, reasonable inference from the answer's "
    "content rather than restating it - e.g. if the answer lists specific named "
    "options, ask how many there are; if the answer states everything included or "
    "charged, ask whether anything is hidden or extra.\n"
    "Do not mention silver or any product this platform doesn't offer. Do not ask "
    "about anything not actually stated or reasonably inferable from the answer. "
    "Return ONLY a JSON array of 10 strings, "
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
