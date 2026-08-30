# Real-Scenario Testing

A hand-written, realistic-question eval on top of `backend/scripts/eval_kb.py`/`eval_faq_coverage.py` (which only test FAQ retrieval) and `eval_routing_model.py`/`eval_judgment_model.py` (which only test known failure cases in isolation): this runs **70 questions spanning every kind of message a real customer actually sends** - single-topic FAQ, compound FAQ, transaction-only, redemption order tracking, combined transaction+FAQ, and out-of-scope - through the full, unmocked `chat_turn()` pipeline against a real seeded user's real data, and reports a pass/fail count per category.

## Why this exists

The other evals each test one layer in isolation (retrieval, or a judgment call, or a routing call). This one tests the **whole turn end to end**, the way a customer actually experiences it, and is explicitly designed to include the messy, multi-part phrasing real users send - "how do I buy **and** sell gold?", "can you check my transaction **and** help me buy more?" - not just the clean, single-intent questions the other evals use. It exists because two real bugs (a compound-FAQ question silently dropping half its answer, and a compound transaction+FAQ question only ever addressing one half) were found this way, by hand, before this eval was written to make them repeatable and quantifiable.

## The six categories

| Category | What it tests | Example |
|---|---|---|
| `faq_single` | One question, one FAQ article | "How do I sell my gold?" |
| `faq_combined` | One question spanning **two** FAQ articles | "How do I buy AND sell gold on this platform?" |
| `transaction` | Questions about the user's own transaction history | "Why did my last transaction fail?" |
| `redemption` | Questions about a physical gold redemption order's shipment status | "Where is my order?", "Track my gold coin that's out for delivery" |
| `combined` | One question spanning **both** a transaction lookup and a FAQ topic | "Can you check my transaction and assist me to buy the gold?" |
| `out_of_scope` | Genuine capability gaps, greetings, small talk, and unrelated topics | "What's my account balance?", "Hi", "What's the weather like?", "Can I cancel my redemption order?" |

The `combined` category exists specifically because the router can drop part of a compound question if it isn't dispatched and merged correctly - `_chat_turn`/`StreamedChatTurn` now dispatch *every* tool call a compound question produces (deduped by name) and merge the results (`_merge_responses`), rather than acting on only the first, but the merge's "prefer a transaction-shaped base" rule doesn't yet recognize `REDEMPTION_*` types (see `docs/chat-tool-calling-flow.md`) - this eval is what would catch a regression in that dispatch/merge logic, or expose the redemption gap if a `combined`-style row ever mixed those two tools.

## How it works

1. **The fixture** (`backend/scripts/fixtures/real_scenario_questions.csv`) - 70 hand-written rows, grounded in the actual seeded data (`backend/scripts/seed.py`'s 18 FAQ articles, alice's 7 real transactions, and alice's 5 real redemption orders), not synthetic placeholders. Columns:
   - `question` - the exact message sent
   - `expected_type` - the `ChatResponse.type` expected, with two special values:
     - `TEXT_ANSWER_OR_TRANSACTION` (`combined` rows) - accepts any non-error type, since only one half of the question can be reliably addressed
     - `TEXT_ANSWER_GROUNDED` (`out_of_scope` rows) - requires `TEXT_ANSWER` with `grounded: true`, confirming the turn was actually handled by `respond_directly` and not an accidental `search_knowledge_base` call that happened to come back empty (`insufficient_kb_info` also renders as `TEXT_ANSWER`, just with `grounded: false` - same look to the customer, wrong route)
   - `expected_contains` - semicolon-separated substrings that must **all** appear (case-insensitive) in the response message or its structured data for a pass. For `redemption` rows this is usually the literal status enum value (e.g. `out_for_delivery`) since that's guaranteed present in the structured `data` regardless of how the LLM phrases the message - a much more robust check than depending on wording.

2. **The eval** (`backend/scripts/eval_real_scenarios.py`) - sends every question through `orchestrator.chat_turn()` with a fresh, empty history (each question is an independent first message, not a multi-turn conversation), checks it against the row's expectations, and writes a full results file (`backend/scripts/fixtures/real_scenario_results.csv`) with the actual type/message/pass-fail/reason for every row alongside the original expectation - so a failure can be read back without re-running anything. Each run also writes a timestamped snapshot (`backend/scripts/fixtures/eval_reports/result-<timestamp>.csv`) and an expected-vs-actual confusion matrix (`eval_reports/confusion_matrix-<timestamp>.csv`, expected_type × actual_type counts) alongside it, so a specific historical run can be referenced later even after the main results file is overwritten by a subsequent run.

3. **The report** - printed per-question pass/fail, then a per-category breakdown, then the run's real OpenAI cost (computed from each question's own session log, since `chat_turn()` opens its own per-conversation session scope that shadows any outer one - see the script's comment on `_last_session_cost`).

## Running it

```bash
cd backend
python -m scripts.eval_real_scenarios   # 70 real chat turns, ~$0.15 of OpenAI cost
```

Not part of `pytest` / CI, for the same reason `eval_faq_coverage.py` isn't: a hard pass/fail gate on LLM-judged, real-API-call results would be flaky, and would pressure future changes to game the number rather than genuinely improve behavior. This is a report you read by hand, run after touching routing, judgment, or prompt code. This is a deliberate policy on this project: results are reported as measured, never tuned specifically to raise the score.

## Result history

| Date | Overall | faq_single | faq_combined | transaction | redemption | combined | out_of_scope |
|---|---|---|---|---|---|---|---|
| 2026-08-29 | 49/60 (82%) | 14/15 | 10/10 | 14/15 | n/a | 1/10 | 10/10 |
| 2026-08-30 | 66/70 (94%) | 15/15 | 9/10 | 15/15 | 7/7 | 9/10 | 11/13 |

(The 2026-08-29 row predates both the multi-tool dispatch/merge fix and the redemption feature - `combined` was measuring the old single-tool-per-turn limitation directly. The 2026-08-30 row is the fixture's first run after adding the `redemption` category and 3 more `out_of_scope` rows, taking the total from 60 to 70 questions.)

## What the latest run (2026-08-30) found

- **`redemption`: 7/7.** Every new redemption-tracking row passed, including the ambiguous-selection cases (asking about "my gold coin" when two coins are ongoing) and the single-match cases (phrasing that includes enough status detail to resolve to one order).
- **`faq_combined`: 9/10 - one real regression.** "How do I reset my password, and how do I contact human support?" now returns `ESCALATE` instead of answering the password part first. This isn't a malfunction: `request_human_agent`'s tool description explicitly says it bypasses everything else "regardless of whether their underlying question could otherwise be answered," and "how do I contact human support" is a textbook explicit request. The tradeoff this exposes: **any compound question containing a human-agent request will always escalate and silently drop the other half**, even a trivially answerable one.
- **`combined`: 9/10 - a new ambiguity from the redemption feature itself, not a routing bug.** "Can I get physical delivery, and what's the status of my most recent order?" got answered about a *redemption* order instead of the transaction the row's `expected_contains` assumed. Before redemption tracking existed, "my most recent order" unambiguously meant a transaction; now that word is genuinely overloaded between two real tools. The actual answer given was coherent and correctly grounded - just not what this specific row expected.
- **`out_of_scope`: 11/13 - both failures were the eval's own ground truth being wrong, not the app.** "Can I cancel my redemption order?" and "Can I get a refund for my delivered gold order?" were assumed to need `respond_directly` (a capability-gap reply), but `respond_directly`'s own description explicitly forbids that for any policy/how-to-shaped question, and these are policy-shaped, indistinguishable in form from "can I take physical delivery" (a real FAQ). The app correctly tried `search_knowledge_base` and correctly declined via `insufficient_kb_info` when it found nothing - exactly the intended behavior for a genuine KB gap. These two rows are left marked FAIL in the results file rather than quietly relabeled, since that's the honest record of the assumption going in.
- **`faq_single`: 15/15 (up from 14/15).** The previously-flaky "Where is my gold stored?" row now passes - not something this run's changes targeted, so treat this as one data point, not a confirmed fix, until it's seen passing consistently across further runs.
