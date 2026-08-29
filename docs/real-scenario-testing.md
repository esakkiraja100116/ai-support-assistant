# Real-Scenario Testing

A hand-written, realistic-question eval on top of `backend/scripts/eval_kb.py`/`eval_faq_coverage.py` (which only test FAQ retrieval) and `eval_routing_model.py`/`eval_judgment_model.py` (which only test known failure cases in isolation): this runs **60 questions spanning every kind of message a real customer actually sends** - single-topic FAQ, compound FAQ, transaction-only, combined transaction+FAQ, and out-of-scope - through the full, unmocked `chat_turn()` pipeline against a real seeded user's real data, and reports a pass/fail count per category.

## Why this exists

The other evals each test one layer in isolation (retrieval, or a judgment call, or a routing call). This one tests the **whole turn end to end**, the way a customer actually experiences it, and is explicitly designed to include the messy, multi-part phrasing real users send - "how do I buy **and** sell gold?", "can you check my transaction **and** help me buy more?" - not just the clean, single-intent questions the other evals use. It exists because two real bugs (a compound-FAQ question silently dropping half its answer, and a compound transaction+FAQ question only ever addressing one half) were found this way, by hand, before this eval was written to make them repeatable and quantifiable.

## The five categories

| Category | What it tests | Example |
|---|---|---|
| `faq_single` | One question, one FAQ article | "How do I sell my gold?" |
| `faq_combined` | One question spanning **two** FAQ articles | "How do I buy AND sell gold on this platform?" |
| `transaction` | Questions about the user's own transaction history | "Why did my last transaction fail?" |
| `combined` | One question spanning **both** a transaction lookup and a FAQ topic | "Can you check my transaction and assist me to buy the gold?" |
| `out_of_scope` | Genuine capability gaps, greetings, small talk, and unrelated topics | "What's my account balance?", "Hi", "What's the weather like?" |

The `combined` category exists specifically because the current architecture only ever routes to **one** tool per turn (`search_knowledge_base` *or* `get_recent_transactions` *or* `respond_directly`, never more than one) - so a question needing two of them can only ever get half an answer. This eval doesn't try to hide that; it measures exactly how often it happens, so the decision to build (or not build) multi-tool routing can be based on a real number instead of a guess.

## How it works

1. **The fixture** (`backend/scripts/fixtures/real_scenario_questions.csv`) - 60 hand-written rows, grounded in the actual seeded data (`backend/scripts/seed.py`'s 20 FAQ articles and alice's 7 real transactions), not synthetic placeholders. Columns:
   - `question` - the exact message sent
   - `expected_type` - the `ChatResponse.type` expected, with two special values:
     - `TEXT_ANSWER_OR_TRANSACTION` (`combined` rows) - accepts any non-error type, since only one half of the question can be addressed today
     - `TEXT_ANSWER_GROUNDED` (`out_of_scope` rows) - requires `TEXT_ANSWER` with `grounded: true`, confirming the turn was actually handled by `respond_directly` and not an accidental `search_knowledge_base` call that happened to come back empty (`insufficient_kb_info` also renders as `TEXT_ANSWER`, just with `grounded: false` - same look to the customer, wrong route)
   - `expected_contains` - semicolon-separated substrings that must **all** appear (case-insensitive) in the response message or its structured data for a pass

2. **The eval** (`backend/scripts/eval_real_scenarios.py`) - sends every question through `orchestrator.chat_turn()` with a fresh, empty history (each question is an independent first message, not a multi-turn conversation), checks it against the row's expectations, and writes a full results file (`backend/scripts/fixtures/real_scenario_results.csv`) with the actual type/message/pass-fail/reason for every row alongside the original expectation - so a failure can be read back without re-running anything.

3. **The report** - printed per-question pass/fail, then a per-category breakdown, then the run's real OpenAI cost (computed from each question's own session log, since `chat_turn()` opens its own per-conversation session scope that shadows any outer one - see the script's comment on `_last_session_cost`).

## Running it

```bash
cd backend
python -m scripts.eval_real_scenarios   # 60 real chat turns, ~$0.10 of OpenAI cost
```

Not part of `pytest` / CI, for the same reason `eval_faq_coverage.py` isn't: a hard pass/fail gate on LLM-judged, real-API-call results would be flaky, and would pressure future changes to game the number rather than genuinely improve behavior. This is a report you read by hand, run after touching routing, judgment, or prompt code.

## Result history

| Date | Overall | faq_single | faq_combined | transaction | combined | out_of_scope |
|---|---|---|---|---|---|---|
| 2026-08-29 | 49/60 (82%) | 14/15 | 10/10 | 14/15 | 1/10 | 10/10 |

## What this run found

- **`faq_combined` and `out_of_scope`: 100%.** Both were fixes made earlier the same day (merging multiple `answer_from_kb` tool calls instead of keeping only the last one; tightening `respond_directly`'s routing so it isn't used as an uncertainty fallback) - this eval is what confirmed both actually work under realistic phrasing, not just the one case each was originally found from.
- **`combined`: 1/10 (10%).** The one real number this eval exists to produce. Confirms the known single-tool-per-turn limitation isn't a rare edge case - it's the *typical* outcome for a question spanning both domains. Worth weighing against the cost of building multi-tool routing, now that the size of the gap is measured rather than assumed.
- **Two smaller `transaction` gaps**: asking for a computed *total* across transactions gets a per-transaction list instead of a sum, and asking for a transaction's *date* can get the failure reason instead - both are generation-completeness gaps in the explanation prompts, not routing or retrieval issues.
- **One `faq_single` miss** ("Where is my gold stored?") - the same routing-decline pattern documented in `docs/chat-tool-calling-flow.md`, still not fully eliminated by the `tool_choice="required"` fix, consistent with that fix's own measured ~80% (not 100%) success rate.
