# Judgment-Step Model Comparison: gpt-4o-mini vs. gpt-5.6-sol

The knowledge-base flow makes two decisions per question: which tool to call (intent routing), and — once articles are retrieved — whether they actually answer the question (`answer_from_kb` vs. `insufficient_kb_info`, see the root README's "trust boundary" section). This compares two models for that second decision, the **judgment step**, with everything else (retrieval, intent routing, embeddings) held constant.

## Setup

- Fixture: `scripts/fixtures/faq_variations.json` — 180 questions (18 FAQs × 10), generated from both question *and* answer content (see `docs/faq-coverage-testing.md`).
- Both runs made with the intent-routing fix in place (see "What changed" below) — this fix was applied before *either* run, so it isn't part of what's being compared here.
- `gpt-5.6-sol` used `reasoning_effort=none`, since this model rejects tool-calling combined with any other reasoning effort level on the Chat Completions API (would require the separate Responses API to use real reasoning + tools together — not attempted here).
- Run via `scripts/eval_faq_coverage.py`, which calls the real `chat_turn()` — the same function `POST /chat` uses, not a shortcut.

```bash
python -m scripts.eval_faq_coverage
python -m scripts.eval_faq_coverage --judgment-model gpt-5.6-sol --judgment-reasoning-effort none
```

## Results

| Metric | gpt-4o-mini | gpt-5.6-sol |
|---|---:|---:|
| Answered | 157/180 (87.2%) | 166/180 (92.2%) |
| Declined ("I don't have enough information") | 21/180 | 12/180 |
| Misrouted to transaction path | 2/180 | 2/180 |
| Errored | 0/180 | 0/180 |
| **Total cost (180 questions)** | **$0.0360** | **$0.6620** |
| Avg cost / question | $0.00020 | $0.00368 |

**+9 questions answered, +5.0 points accuracy, for ~18.4x the cost** (+$0.626 total, both trivial in absolute terms).

The 2 misrouted questions are identical in both runs — both are personal-phrasing variants of the "why might a transaction fail" FAQ ("why did **my** transaction fail") that legitimately route to the transaction tool per the system prompt, not a judgment-step difference.

## What actually improved

Cross-referencing declines against known source FAQs (see `docs/faq-coverage-testing.md`'s methodology), every prior real judgment failure we manually diagnosed this session was **retrieved correctly by both models** — the gap is purely in willingness to infer an answer from stated facts rather than requiring near-literal wording, e.g.:

- "What payment methods are available?" → inferred from an answer that names UPI/card/net banking without a literal "payment methods" phrase
- "What do I need to do to access Recurring Plans?" → inferred from "go to Recurring Plans in your account settings"
- "During what hours is human support available?" → inferred from "during business hours"

`gpt-5.6-sol` made these connections consistently; `gpt-4o-mini` did not, even with the same inference-permitting tool description (see `tools_schema.py`'s `answer_from_kb`).

**Neither model fixes retrieval-miss cases** — e.g. "What percentage should I expect for the **spread**?" (the word "spread" only exists in the fees answer, never the question, so the article never reaches either model's candidate pool). That's a separate, still-open issue (see "What I'd try next").

## What changed before this comparison (not part of it)

An intent-routing bug was found and fixed during this investigation, applied to *both* runs above: the system prompt's carve-out for "I can't answer your personal holdings/balance" was over-triggering on product-catalog questions like "How many carats of gold are available?" (pattern-matching "available" to "holdings"), causing the intent router to decline the question *before* even attempting a knowledge-base search — a different, earlier-stage failure than anything in the table above. Fixed by clarifying the prompt to distinguish "the customer's own portfolio" from "what the platform offers in general" (`tools_schema.py`).

## Is 18.4x the cost worth +5 points, always?

Not necessarily as an all-or-nothing swap. A cheaper middle ground discussed but not yet implemented: **escalate only on decline** — try `gpt-4o-mini` first, and only re-ask the same question with `gpt-5.6-sol` when it returns `insufficient_kb_info`, never on a question it already answered. Rough projected cost: ~21 escalations × ~$0.0035/call ≈ $0.07, plus the $0.036 baseline ≈ **~$0.11 total** — about 6x cheaper than always using `gpt-5.6-sol`, while likely recovering most of the same fixable declines (not the retrieval-miss ones, which no judgment model can fix). Not implemented or measured yet as of this writing.

## What I'd try next

- Measure the escalate-on-decline cascade above for a real number instead of a projection.
- Answer-embedding (see root README's "what I'd improve") to fix retrieval-miss cases like "spread" that no judgment model change can reach.
- Test `gpt-5.6-sol` via the `/v1/responses` API with real reasoning effort (not `none`) to see if the remaining declines improve further - untested here due to the Chat Completions tool-calling restriction.
