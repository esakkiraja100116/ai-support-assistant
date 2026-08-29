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

## Current result: 175/180 (97.2%)

Run on 2026-08-29, no code changes made in response to it (see note below):

- 0 errors.
- 2 "misrouted" — both were phrasings that the fixture generator personalized ("why did **my** gold transaction fail?") in a way that changed the actual intent from a generic policy question into a personal one. The system prompt correctly routes personal transaction questions to the transaction tool instead of the knowledge base — this is arguably correct behavior given the literal wording, not a retrieval failure.
- 3 genuine declines — indirect phrasings ("automatic gold purchase plan," "vaults where my gold is placed") that the answer-judgment step was conservative about connecting to the relevant FAQ, despite the FAQ being in its candidate list. Same category as a bug found earlier ("are there hidden charges" not connecting to the fees FAQ) — a prompt-wording tuning knob (nudging the model to make reasonable inferential connections, not just literal keyword matches), not a structural issue.

**Deliberately not chased further**: per the project's "don't overfit" principle, no prompt or retrieval code was changed specifically to push this number up after this run. The current architecture (widen the candidate pool, let the model judge relevance from real content — see the root README's "Embeddings and knowledge-base retrieval" section) is doing its job; squeezing out the last few percent by hand-tuning against this exact 180-question set would optimize for the test rather than for real users asking questions the fixture never anticipated.
