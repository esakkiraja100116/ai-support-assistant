# AI Customer Support Assistant

A full-stack support chat for a platform where customers buy and sell gold. It answers general questions from an approved knowledge base, and — for questions about a customer's own orders — looks up their real transaction data through authorized backend tools rather than letting an LLM guess.

- **Frontend**: Next.js (App Router, TypeScript) — see [frontend/README.md](frontend/README.md)
- **Backend**: FastAPI (Python) — see [backend/README.md](backend/README.md)
- **Database**: PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) (semantic search over the FAQ knowledge base)
- **LLM provider**: OpenAI (`gpt-4o-mini` for chat/tool-calling, `text-embedding-3-small` for embeddings) — configurable via `backend/.env`

## Quick start

```bash
docker compose up -d db                      # Postgres + pgvector on :5433

cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                          # set OPENAI_API_KEY and a real JWT_SECRET
alembic upgrade head
python -m scripts.seed                        # seeds users, transactions, and embeds the FAQ articles
uvicorn app.main:app --reload --port 8000

# in a second terminal
cd frontend
npm install
cp .env.example .env.local
npm run dev                                   # http://localhost:3000
```

Full setup/run/test details live in each service's own README. If you're using Claude Code, `.claude/skills/setup-repo/` has this same bootstrap as a skill it can run for you.

## The two core flows

**General support question** ("How do I sell my gold?") → the backend embeds the question, searches the knowledge base with pgvector, and answers using *only* the retrieved content. If nothing matches well enough, it says so instead of guessing.

**Transaction question** ("Why did my last purchase fail?") → the backend fetches the authenticated customer's own recent transactions (never anyone else's), tries to work out from their wording which single transaction they mean, and either explains that one directly or — if it's genuinely unclear — shows the list as clickable cards for the customer to pick from.

## Architecture

```
Browser (Next.js)
   │  fetch + Bearer JWT
   ▼
FastAPI  ──────────────────────────────────────────────┐
   │                                                    │
   │  POST /chat                                        │  POST /transactions/{id}/explain
   ▼                                                    ▼
orchestrator.chat_turn()                     transaction_service.get_transaction_details()
   │                                          (plain authorized lookup, 404 if not caller's)
   │  1 OpenAI call, tool_choice="auto"                 │
   │  tools: search_knowledge_base,                     │  1 OpenAI call: explain this JSON record
   │         get_recent_transactions                    ▼
   ├─ no tool called ──────────► small-talk reply   TRANSACTION_EXPLANATION
   │
   ├─ search_knowledge_base ──► kb_service (pgvector cosine search)
   │                             │
   │                             ├─ below threshold ──► fixed "I don't know" (no 2nd LLM call)
   │                             └─ above threshold ──► 1 more OpenAI call, grounded in the
   │                                                     retrieved article text only
   │
   └─ get_recent_transactions ─► transaction_service (DB rows scoped to current_user)
                                  │
                                  │  1 more OpenAI call, tool_choice="required"
                                  │  tools: resolve_transaction, no_single_match
                                  ├─ resolve_transaction(id) ──► id checked against the
                                  │                               already-fetched list ──►
                                  │                               1 more OpenAI call to explain
                                  │                               it ──► TRANSACTION_EXPLANATION
                                  └─ no_single_match(reason) ──► TRANSACTION_SELECTION
                                                                  (fixed message + real DB rows)
```

Postgres (with pgvector) sits behind the backend; nothing in the diagram above ever gives the model direct database access — every arrow into Postgres is a plain Python query the server runs itself.

### The trust boundary: how tool-calling is used, and why

The one rule that shapes almost every design decision here: **the LLM never gets to read or write the database directly, and it never gets to decide who it's looking data up for.**

Concretely:

- `app/services/tools_schema.py` defines every tool schema the model can call. None of them accept a `user_id` parameter — `get_recent_transactions` takes zero arguments. The authenticated user is bound server-side from the JWT (`app/auth/dependencies.py::get_current_user`) before any tool executes, so there's no field for the model to fill in, guess, or be prompt-injected into supplying.
- When the model *does* pick a specific transaction (via `resolve_transaction(transaction_id)`), the backend never runs a fresh, unscoped DB query for that id. It looks it up in `txn_by_id`, a dict built from the list it **already fetched for that user a moment earlier** (`orchestrator.py::_handle_recent_transactions`). If the model names an id that isn't in that dict — hallucinated, or an attempted injection — the lookup just returns nothing and the code falls back to the safe selection list. A wrong or malicious id can never leak another customer's transaction; there is no code path where a model-supplied id reaches the database directly.
- The knowledge-base and transaction-detail LLM calls are always given a closed, pre-fetched, already-authorized chunk of data (a handful of retrieved articles, or one JSON transaction record) and instructed to answer *only* from it. There's no "here's the whole database, go find the answer" prompt anywhere in this codebase.
- **Two decision points, four tool schemas.** The first OpenAI call (`tool_choice="auto"`) picks between `search_knowledge_base` and `get_recent_transactions` — this is intent routing. If it picks the transaction path, a *second* OpenAI call (`tool_choice="required"`) picks between `resolve_transaction` and `no_single_match` — this is disambiguation. Forcing a tool choice at that second step (rather than letting the model reply in plain text) matters: an earlier version let it "just reply" when it couldn't resolve one transaction, and it would sometimes narrate the whole transaction list back as Markdown prose — redundant with the card UI, and a live example of exactly the kind of ungoverned LLM output the assignment's structured-response requirement exists to prevent. Making both outcomes (`resolve_transaction` / `no_single_match`) into tool calls means the model's only way to communicate is through a shape the server already validates and controls; the two possible UI-facing messages (`"Here are your recent transactions:"` / `"Which transaction are you referring to?"`) are fixed strings the server chooses, never text the model writes.
- The result: **structured responses, not parsed prose.** Every backend response is a `{type, message, data}` shape (`app/schemas/chat.py`). The frontend switches on `type`; `message` is always just prose to display, never something the UI has to interpret to figure out what happened.

### Embeddings and knowledge-base retrieval

The knowledge base is a table of FAQ articles (`support_articles`: question, answer, category). Answering from it well — without hallucinating when it doesn't have an answer — comes down to knowing which stored article is actually about what the customer just asked, without hand-writing keyword rules for every phrasing.

An **embedding** is a vector of numbers (1536 of them, from OpenAI's `text-embedding-3-small`) that a model produces for a piece of text such that texts with similar *meaning* end up as vectors that are close together in that 1536-dimensional space — "How do I sell my gold?" and "What's the process to liquidate my holdings?" land near each other even though they share almost no words. "Closeness" is measured with **cosine similarity** (1 minus cosine distance): 1.0 means identical direction (same meaning), 0 means unrelated, negative means opposite.

How this is used here (`app/services/kb_service.py`):

1. At seed time (`scripts/seed.py`), every FAQ article's **question text** gets embedded once and stored in its `embedding` column (a native `pgvector` column, `VECTOR(1536)`).
2. At query time, the customer's **own message, verbatim**, is embedded the same way, and pgvector's `<=>` cosine-distance operator (exposed in SQLAlchemy as `.cosine_distance()`) finds the closest stored articles directly in SQL — `ORDER BY embedding <=> :query_vector LIMIT 3`. No separate vector database, no manual similarity math in Python.
3. If the best match's similarity is below `KB_SIMILARITY_THRESHOLD` (0.65, tuned empirically — see below), the request is treated as **not grounded**: the backend returns a fixed "I don't have enough information" answer and skips the second LLM call entirely. This is the concrete mechanism behind "say you don't know rather than hallucinate" — it's a structural gate, not a prompt instruction the model could ignore.
4. Above the threshold, the matched article(s) are passed to one OpenAI call with an explicit "answer only from this text" system prompt, and the response is tagged `grounded: true` with the source article ids.

**Two real retrieval bugs this surfaced, both worth calling out:**

- *Embedding the wrong text.* Articles were originally embedded on `question + answer` combined, which diluted the vector enough that the exact seeded question "How do I sell my gold?" only scored 0.74 against itself. Switching to embedding the **question text alone** fixed it (exact match → 1.0 similarity) — customer messages arrive as questions, so question-to-question similarity is a much cleaner signal than question-to-(question+answer) similarity. This is why `scripts/seed.py` embeds `question`, not `f"{question} {answer}"`.
- *Letting the model rephrase the search query.* The `search_knowledge_base` tool originally let the intent-routing model rewrite the customer's message into a "search query" before it got embedded. Measured with `scripts/eval_kb.py` (a small standing eval script — 11 test queries, run by hand when tuning retrieval), this hurt more than it helped: rewording even slightly — "How can I exchange my **gold for cash**?" → "how to exchange gold for cash" — dropped the score from 0.799 to 0.733, flipping a genuine match to a false "I don't know." The rephrasing step was removed entirely; `search_knowledge_base` now takes no arguments, and the customer's raw message is always what gets embedded and searched.

After both fixes, the threshold was re-tuned from 0.75 down to 0.65 against that same eval script: real paraphrases ("exchange for cash," "liquidate my holdings," "cash out") now score 0.74–0.81 and pass, while genuinely off-topic or unanswered questions ("What is the capital of France?", "international wire transfers") still correctly score under 0.42. One narrower synonym case ("insured **against theft**" vs. the seeded "Is my investment insured?", 0.637) still falls just short — a real residual gap from a bare cosine cutoff rather than something worth chasing by hand-tuning against one more query; see "what I'd improve" for the actual fix (letting the LLM judge relevance over a looser pre-filter, instead of a single hard number).

pgvector's exact (brute-force) distance search is used rather than an approximate index (HNSW/IVFFlat) — with ~18 seed articles, exact search is both simpler and faster than building an index; see "what I'd improve" below for what changes at real scale.

### Conversations, sessions, and why the backend stays stateless

The backend keeps no server-side conversation or session store — every `POST /chat` call is handed everything it needs (`message` + a trimmed `history` array) and forgets it the moment it responds. All conversation continuity lives in the browser:

- The **conversation id lives in the URL** (`?c=<uuid>`, minted by the frontend on login or "New chat"), not in any backend table.
- The frontend keeps the message list in React state, mirrors it to `sessionStorage` keyed by `(userId, conversationId)`, and sends the last 10 turns back as `history` with every request.
- For a turn that showed a transaction list, the *actual transaction records* — not just the assistant's one-line reply — are folded into that history entry, so a later "the second one" can still be resolved by the LLM even though the server itself never stored the list anywhere.

This keeps the backend simple and horizontally stateless at the cost of conversations not surviving a browser/device switch — a deliberate trade-off for this scope, listed below as the first thing to change for production.

## Testing

```bash
cd backend && pytest
```

17 tests, all deterministic and offline (every OpenAI call is monkeypatched at the `llm_client` seam — no network access or API key needed). The two highest-value ones:

- **`test_transaction_authz.py`** — user A's JWT can fetch their own transaction (200) but never user B's (404), and `/transactions/recent` never returns another user's rows. This is the literal trust boundary described above, under test.
- **`test_kb_grounding.py`** — asserts the below-threshold path returns `grounded: false` *and* that the second ("write the grounded answer") LLM call is never invoked in that case — the no-hallucination guard is tested as a structural fact, not just a prompt.

## What I would improve for production

- **Security**: replace the no-password mock login with real authentication; add rate limiting on `/chat` (each call can trigger 1–3 OpenAI requests); add request size limits and stricter CORS in production.
- **Observability**: structured logging/tracing per `conversation_id` showing which tool was called and why, latency per LLM call, and a dashboard for KB grounding rate (how often customers hit the "I don't know" fallback — a proxy for content gaps).
- **Scalability**: persist conversations server-side (Postgres or Redis) instead of trimmed client-sent history, so a conversation survives a device switch and doesn't grow unbounded on the client; add an HNSW index on `support_articles.embedding` once the KB is large enough that brute-force search matters.
- **Retrieval quality**: replace the single hard cosine cutoff with a loose pre-filter (just to drop obviously unrelated noise) followed by having the grounded-answer LLM call itself judge whether the retrieved content actually answers the question — more robust to synonym/paraphrase variance than any one fixed threshold number can be. Also: chunk longer articles instead of one-embedding-per-FAQ, add reranking for borderline-similarity results, and surface citations in the UI (the backend already returns `sources`, the frontend doesn't show them yet).
- **Cost**: cache embeddings for repeated/similar queries; consider a cheaper/faster model for the intent-routing and resolve steps versus the final answer-generation step.
- **Escalation**: a "hand off to a human agent" action when the KB has no grounded answer twice in a row, or when a transaction explanation can't be generated — right now the fallback message just apologizes.
