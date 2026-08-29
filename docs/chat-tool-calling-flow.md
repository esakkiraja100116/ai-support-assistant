# Chat & Tool-Calling Flow

How `POST /chat` (and its streaming counterpart, `POST /chat/stream`) actually decides what to do internally: which model runs at each step, which tools it can call, and how the result gets shaped into a response. This reflects the code as of 2026-08-29 (`backend/app/services/orchestrator.py`), including the intent-routing fix, `respond_directly` (replacing the old "no tool called" escape hatch), the multi-article merge fix for compound KB questions, and the streaming variant. See `docs/real-scenario-testing.md` for the 60-question eval this architecture is measured against, and `docs/faq-coverage-testing.md`/`docs/judgment-model-comparison.md` for the earlier, narrower evals that found the KB judgment issues.

## Model details

| Step | Default model | Tools available | `tool_choice` | Can be overridden? |
|---|---|---|---|---|
| 1. Intent routing | `gpt-4o-mini` (`settings.chat_model`) | `search_knowledge_base`, `get_recent_transactions`, `request_human_agent`, `respond_directly` | **`required`** | Yes — `routing_model` / `routing_reasoning_effort`, experiment-only (see `scripts/eval_routing_model.py`) |
| 2a. KB judgment | `gpt-4o-mini` | `answer_from_kb`, `insufficient_kb_info` | `required` | Yes — `judgment_model` / `judgment_reasoning_effort`, experiment-only (see `docs/judgment-model-comparison.md`) |
| 2b. Transaction resolve | `gpt-5.6-sol` (`settings.resolve_model`) | `resolve_transactions`, `no_single_match` | `required` | No |
| 3. Transaction explain | `gpt-4o-mini` | *(none — plain text generation)* | n/a | No |
| Embeddings (seed + query) | `text-embedding-3-small` | n/a | n/a | No |

**`tool_choice: required` at the routing step (step 1)** is the most significant change from the original design: the model used to be allowed to skip calling a tool entirely and just answer in free-form prose, which is where every real routing bug found this session came from (see `docs/real-scenario-testing.md`'s "what this run found"). `respond_directly` replaces that escape hatch with an explicit tool - genuine greetings, small talk, and capability gaps (e.g. "how much gold do I own") now go through it instead of silent free-form text, so the router can never respond without picking one of four defined options.

Every call goes through the single seam `app/services/llm_client.py`, which is also where token usage and cost get logged per-session (`app/services/session_log.py`, `app/services/pricing.py`) - or, for the streaming path, via an explicit `TurnMetrics` object rather than that same per-session logging (see "Streaming variant" below for why).

**The authorization boundary, shown as the box at the top of the diagram**: `current_user` is decoded from the request's JWT (`get_current_user`) *before* any of this runs. No tool schema below accepts a `user_id` parameter — the model can never supply, guess, or be prompt-injected into supplying one. See the root README's "trust boundary" section for the full reasoning.

## The flow

Split into three views — one overview plus one detail diagram per branch — rather than a single dense graph.

### 1. Overview: what the first LLM call decides

```mermaid
flowchart TD
    A(["POST /chat"]) --> B["Auth: JWT -> current_user<br/>(server-side only)"]
    B --> C["LLM Call 1 — Intent Routing<br/>gpt-4o-mini · tool_choice: required"]
    C -->|respond_directly| D["Greeting / small talk /<br/>capability gap reply<br/>grounded = true"]
    C -->|search_knowledge_base| E["Knowledge Base path<br/>— see diagram 2"]
    C -->|get_recent_transactions| F["Transaction path<br/>— see diagram 3"]
    C -->|request_human_agent| G["Escalate to human agent"]
```

`tool_choice: required` means the model must always pick at least one of these four - there is no fifth "just answer in free text" option. `respond_directly`'s own tool description explicitly forbids using it as an uncertainty fallback ("never call this just because you are unsure... uncertainty is not a request for a human" applies the same idea to `request_human_agent`) - both were tightened after being observed doing exactly that.

**"At least one," not "exactly one":** a compound question ("check my transactions **and** tell me the fees you charge") correctly makes the model issue *two* tool calls in a single response - `get_recent_transactions` and `search_knowledge_base` together. Every tool call in the response is dispatched (`request_human_agent` present anywhere bypasses everything else, per its own description), and the results are merged into one `ChatResponse`: whichever result is transaction-shaped is used as the base (so the frontend still gets `type`/`data` to render cards or a detail panel), with every other result's message text appended after it. Before this was fixed, only `tool_calls[0]` was ever acted on and the rest were silently dropped - a real-scenario eval (`docs/real-scenario-testing.md`) measured this happening on ~90% of realistic combined questions before the fix.

### 2. Knowledge base path

```mermaid
flowchart TD
    A["search_knowledge_base()"] --> B["Embed query + pgvector search<br/>top 8 candidates"]
    B --> C{"Any candidate<br/>≥ 0.30 similarity?"}
    C -->|No| D["Decline:<br/>'I don't have enough information'<br/>no further LLM call"]
    C -->|"Yes (1–8)"| E["LLM Call 2a — KB Judgment<br/>gpt-4o-mini · tool_choice: required"]
    E -->|"answer_from_kb<br/>(one or more calls)"| F["Merge cited articles + answers<br/>across every answer_from_kb call<br/>grounded = true"]
    E -->|insufficient_kb_info| D
```

*Sources are validated against the candidates just fetched — never a fresh, unscoped lookup by whatever id the model names.*

*A compound question ("how do I buy **and** sell gold?") can make the model issue **multiple separate** `answer_from_kb` calls - one per sub-question - instead of one call citing every relevant article together, even though the schema already supports citing several ids per call. The code merges every `answer_from_kb` call it receives (concatenating their answer text, unioning their cited ids) rather than acting on only the first or last one seen - see `docs/real-scenario-testing.md`'s `faq_combined` category, which is what caught this.*

### 3. Transaction path

```mermaid
flowchart TD
    A["get_recent_transactions()"] --> B["Fetch current_user's own<br/>transactions only"]
    B --> C{"Any transactions?"}
    C -->|No| D["'No recent transactions yet'"]
    C -->|Yes| E["LLM Call 2b — Resolve<br/>gpt-4o-mini · tool_choice: required<br/>context: full fetched list as JSON"]
    E -->|resolve_transactions ids| F{"Ids in the list<br/>just fetched?"}
    E -->|no_single_match| G["Show transaction cards<br/>(fixed message + real DB rows)"]
    F -->|Yes| H["LLM Call 3 — Explain<br/>one JSON record only, no tools"]
    F -->|"No (hallucinated / injected id)"| G
    H --> I["Transaction explanation"]
```

*A model-supplied id is only ever checked against the list already fetched for this user — never re-queried against the database, so a wrong or malicious id can't leak another customer's transaction.*

### Error handling (all three paths)

Not drawn as edges above to keep the diagrams readable, but applies uniformly: any exception in an LLM call, the DB, or an unsupported tool name is caught, logged server-side with the full traceback, and returned to the client as a generic `ERROR` response — never a stack trace or internal detail.

## A separate, simpler path: clicking a transaction card

`POST /transactions/{id}/explain` (triggered by clicking a card in the UI, not by typing a message) **does not go through any of the above** — no intent routing, no tool-calling at all:

```mermaid
flowchart LR
    CLICK(["Card clicked in UI"]) --> LOOKUP["transaction_service.get_transaction_details(db, current_user, id)<br/>filtered by id AND user_id = current_user.id"]
    LOOKUP --> OWNS{"belongs to<br/>current_user?"}
    OWNS -->|no| NF["404 Not Found<br/>(not 403 - doesn't confirm the id exists for someone else)"]
    OWNS -->|yes| CALL["LLM Call - Explain<br/>model: gpt-4o-mini, no tools<br/>input: ONE JSON transaction record only"]
    CALL --> RESULT["TRANSACTION_EXPLANATION"]
```

This is deliberate: a card click is already an unambiguous, explicit action, so routing it through NL intent classification would add latency, cost, and a hallucination surface for no benefit (see `explain_transaction`'s docstring in `orchestrator.py`).

If the request includes a `conversation_id`, the click is still persisted as a real turn in that conversation (a synthetic user message - "What can you tell me about transaction X?" - plus the explanation) so a later typed follow-up ("why is it pending?") has the clicked transaction in its history, exactly as if the customer had typed the question. This does not add any intent-routing step to the click itself.

## Streaming variant

`POST /chat/stream` and `POST /transactions/{id}/explain/stream` mirror everything above, with one structural difference: any step that generates free text for the customer (transaction explain/summary, the KB answer, and the `respond_directly` reply) is split into **judge, then generate**, so the generation half can stream token-by-token instead of arriving as one blocking response:

- `respond_directly` and `answer_from_kb` keep the same tool-calling judgment step (deciding *that* this is small talk, or *which* articles apply), but no longer carry the reply/answer text in their arguments - a separate plain-content call (streamed via `llm_client.stream_chat_completion`) writes the actual text afterward, using a small dedicated prompt (`small_talk_reply.j2`, `kb_answer_stream.j2`).
- Transaction explain/summary were already plain content generation, so they stream directly with no restructuring.
- Fixed/lookup responses with nothing to generate (transaction list, escalation, KB decline, errors) are sent as a single immediate event - there's nothing to stream.

This is a fully parallel implementation (`orchestrator.StreamedChatTurn`/`chat_turn_stream`, `tools_schema.ALL_TOOLS_STREAM`) - the non-streaming functions described above are untouched, still used by `/chat`, both eval scripts, and every non-streaming test. Two things about it are non-obvious enough to call out:

- **No shared session/cost tracking with the non-streaming path.** `TurnMetrics` is a plain object held directly on `StreamedChatTurn`, passed explicitly into every LLM call it makes, rather than the contextvar-based `turn_scope()`/`session_log.session_scope()` the non-streaming path uses. Contextvars don't survive being set/reset across the different worker-pool threads a sync generator driven by Starlette's `StreamingResponse` can run on - this was a real bug found by testing the streaming endpoint live, not a design preference. Streamed turns also don't get a JSONL session log entry (observability gap only; persistence goes through `conversation_service`, unaffected).
- **Every streaming request opens its own SQLAlchemy session on a dedicated worker thread**, rather than using the `get_db()` dependency at all - the same threading issue extends to `Session` objects, which broke (and in one variant, hung) when a `db` handed off between threads was used mid-stream. See `routers/chat.py`'s `chat_stream` for the full comment.
