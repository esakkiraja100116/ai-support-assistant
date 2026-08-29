# Knowledge Base Coverage Testing

A larger, repeatable retrieval eval on top of `backend/scripts/eval_kb.py`'s 11-query check: instead of a handful of hand-picked questions, this runs **10 alternative phrasings of every seeded FAQ (18 × 10 = 180 questions)** through the real chat pipeline and reports how many were actually answered.

## Why this exists

`eval_kb.py` catches specific regressions (a known bug, a known paraphrase) but doesn't tell you the *overall* health of retrieval across realistic phrasing variety. This does — and because it runs the same `chat_turn()` function `POST /chat` calls (not a shortcut, not a mock), a result here reflects exactly what a real customer would get.

## How it works

1. **Generate the fixture** (`backend/scripts/generate_faq_variations.py`): for each of the 18 seeded FAQ articles, one LLM call asks for 10 alternative customer phrasings of the same underlying question — varying formality, directness, and word choice, explicitly excluding out-of-scope products (e.g. silver, which this platform doesn't sell). The result is committed to the repo as `backend/scripts/fixtures/faq_variations.json` — a **fixed, reviewable** 180-question set, not regenerated on every run. Re-run this script only when you want a fresh set of variations.

2. **Run the eval** (`backend/scripts/eval_faq_coverage.py`): every one of the 180 questions is sent through `orchestrator.chat_turn()` with a fresh, empty history, and the response is classified:
   - **answered** — `TEXT_ANSWER` with `grounded: true` (the knowledge base actually answered it)
   - **declined** — `TEXT_ANSWER` with `grounded: false` (the assistant said it didn't have enough information)
   - **misrouted** — anything else (e.g. `TRANSACTION_SELECTION` — the intent router sent it down the transaction path instead of the KB path)
   - **error** — an exception was raised

   All 180 questions run under one shared `conversation_id`, so every LLM call, tool call, and the running cost total get logged to one file: `backend/logs/eval-faq-coverage-<timestamp>.jsonl` — the exact same session logging every real `/chat` request goes through (see `backend/README.md`'s "Session logging & cost tracking" section).

3. **Read the report**: the script prints per-FAQ coverage (`X/10 covered`) and an overall total, plus the run's OpenAI cost.

## Running it

```bash
cd backend
python -m scripts.generate_faq_variations   # only if you want a fresh fixture; costs ~18 LLM calls
python -m scripts.eval_faq_coverage         # ~180 chat turns, a few cents of OpenAI cost
```

Not part of `pytest` / CI — a hard pass/fail threshold on 180 LLM-judged answers would be flaky, and worse, would pressure future changes to game the number rather than genuinely improve retrieval. This is a report you read, run by hand after touching retrieval or prompt code.

## Result history

The fixture and prompts both evolved during initial testing, so results aren't directly comparable across rows - each is against the fixture/prompt version active at the time:

| Date | Fixture | Judgment prompt | Answered |
|---|---|---|---|
| 2026-08-29 (early) | question-paraphrases only | original (one example) | 175/180 (97.2%) |
| 2026-08-29 (later) | question **+ answer** based (harder, current) | original (one example) | 159/180 (88.3%) |
| 2026-08-29 (current) | question + answer based | generalized inference examples + intent-routing fix | **157/180 (87.2%)** |

The current baseline (157/180, `gpt-4o-mini`) is lower than the first run not because anything regressed, but because the fixture itself got harder on purpose (see "How it works" above) - it now includes questions that require reading the answer, not just paraphrasing the question. See `docs/judgment-model-comparison.md` for a same-fixture comparison against a different judgment-step model (`gpt-5.6-sol`: 166/180, 92.2%, at ~18x the cost).

Of the current 23 non-answered (21 declined + 2 misrouted):

- 2 "misrouted" — phrasings the fixture generator personalized ("why did **my** gold transaction fail?") in a way that changed the actual intent from a generic policy question into a personal one. The system prompt correctly routes personal transaction questions to the transaction tool instead of the knowledge base - arguably correct behavior given the literal wording, not a failure.
- Most of the rest are the same category as a bug found earlier ("are there hidden charges" not connecting to the fees FAQ despite the article being retrieved) - the judgment step being conservative about inferring an answer from stated facts rather than requiring near-literal wording. A prompt tweak (see `tools_schema.py`'s `answer_from_kb`) measurably helped but didn't fully close this gap with `gpt-4o-mini`; see `docs/judgment-model-comparison.md` for how a different judgment model performs on the same fixture.
- A smaller number are genuine retrieval misses (e.g. "spread" only appearing in an answer, never the question it's embedded from) - not fixable by prompt or model changes to the judgment step; would need indexing answer text too (see root README's "what I'd improve").

**Deliberately not chased further by hand-tuning this exact fixture**: per the project's "don't overfit" principle, changes made in response to these results (the inference-permitting prompt tweak, the intent-routing fix) were general architectural/prompt corrections applicable beyond this specific question set, not patches targeted at individual failing questions. Squeezing out the last few percent by hand-tuning against this exact 180-question set would optimize for the test rather than for real users asking questions the fixture never anticipated.
