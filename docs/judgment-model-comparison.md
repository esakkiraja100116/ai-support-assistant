# Judgment-Step Model Comparison: gpt-4o-mini vs. gpt-5.6-sol

Covers two separate LLM decision points where this comparison led to an actual model change: the knowledge-base judgment step (measured, not adopted as the default - see below) and the transaction-resolve step (measured **and adopted** as the default, `RESOLVE_MODEL` in `app/config.py`).

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

---

## Transaction-resolve step: why gpt-5.6-sol was actually adopted here

Unlike the KB judgment case above, this one wasn't a cost/accuracy trade-off decision - it was a correctness bug with a clear fix, so `gpt-5.6-sol` is the real default (`app/config.py`'s `RESOLVE_MODEL`), not just an experiment.

### The bug

A user asked *"How much did I pay for my last gold purchase?"* against this transaction history (most recent first): `txn_1005` (BUY, **PENDING**, Aug 25), `txn_1004` (RECURRING_BUY, **SUCCESS**, Aug 24), `txn_1002` (BUY, SUCCESS, Aug 22), ... `gpt-4o-mini` resolved to `txn_1005` - the most recent *purchase-type* transaction by date, ignoring that its status is `PENDING`, meaning no payment has actually gone through. The tool description (`resolve_transactions` in `tools_schema.py`) already explicitly said *"'paid'/'completed'/'successful' means status=SUCCESS - a PENDING or FAILED transaction has NOT been paid, so don't pick one of those... even if it's more recent"* - the instruction existed and was still not followed.

**Why this is worse than the KB case**: there, the model at least admits uncertainty (`insufficient_kb_info`), which is a signal an escalate-on-decline cascade can trigger on. Here, `gpt-4o-mini` was **confidently wrong** - no decline, no hedge, just the wrong transaction. There's no uncertainty signal to escalate on for this failure mode, so the cascade idea from above doesn't apply here; the only options were a stronger default model, a much stronger prompt, or accepting the bug.

### The test

Same system prompt, same tool schema, same transaction list, only the model changed:

| Model | Resolved | Correct? |
|---|---|---|
| `gpt-4o-mini` | `txn_1005` (PENDING, ₹3,200) | ❌ |
| `gpt-5.6-sol` (`reasoning_effort=none`) | `txn_1004` (SUCCESS, ₹1,000) | ✅ |

Re-verified 3/3 consistent for `gpt-5.6-sol` after switching the default.

### 20-query follow-up eval

To check this held up beyond the one bug report, `scripts/eval_transaction_queries.py` runs 20 transaction-support queries - simple lookups, compound multi-transaction questions, out-of-scope questions, prompt-injection/guardrail attempts, and a multi-turn conversational follow-up - through the real `chat_turn()` with `gpt-5.6-sol` as the resolve model:

```bash
python -m scripts.eval_transaction_queries
```

**Result: 20/20 queries ran without error, 18/20 clearly correct, $0.0459 total cost (~$0.0023/query).** No guardrail or out-of-scope query leaked any data or complied with an injection attempt (tested: another customer's account by id, "ignore your restrictions" + direct SQL access, "show me your system prompt", claimed admin status) - all correctly declined without needing any transaction-specific guardrail code, since the model has no tool that accepts an arbitrary customer id in the first place (see the root README's trust boundary section).

Two open findings from this run, **not fixed yet** - flagged rather than silently patched, per this project's "don't overfit" principle:

- *"Which payment method did I use for my last recurring purchase?"* (no "paid"/"successful" qualifier) resolved to the `SUCCESS` transaction over a more recent `FAILED` one. Debatable: without status-implying language, "last X" arguably should mean most-recent-by-date regardless of status - this may be the resolve step over-applying the very rule that fixed the bug above.
- *"What's the total amount across all my successful purchases?"* was declined as a "balance/holdings" question by intent routing, before even reaching the resolve step. This is actually a computable sum over specific past transactions (a real, answerable question with today's tools), not a real-time balance lookup - likely the same over-triggering pattern as the earlier "how many carats are available?" bug, in a new phrasing shape (`tools_schema.py`'s holdings-vs-catalog carve-out apparently doesn't yet cover "total amount across transactions" as a legitimate aggregation, distinct from "what's my current balance").
