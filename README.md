# AI Customer Support Assistant

A full-stack support chat for a platform where customers buy and sell gold. It answers general questions from an approved knowledge base, and — for questions about a customer's own orders — looks up their real transaction data through authorized backend tools rather than letting an LLM guess.

- **Frontend**: Next.js (App Router, TypeScript) — see [frontend/README.md](frontend/README.md)
- **Backend**: FastAPI (Python) — see [backend/README.md](backend/README.md)
- **Database**: PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) (semantic search over the FAQ knowledge base)
- **LLM provider**: OpenAI (`gpt-4o-mini` for chat/tool-calling, `text-embedding-3-small` for embeddings) — configurable via `backend/.env`

## Demo

📹 [v1.0 demo video](https://drive.google.com/file/d/12BKAPZOa-xUKVDwou-XT7dRsfrUrzRAd/view?usp=sharing)

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
   ├─ search_knowledge_base ──► kb_service (pgvector cosine search, top 8 candidates)
   │                             │
   │                             ├─ nothing above the noise floor ──► fixed "I don't know"
   │                             │                                    (no 2nd LLM call)
   │                             └─ 1+ candidates ──► 1 more OpenAI call, tool_choice="required"
   │                                                  tools: answer_from_kb, insufficient_kb_info
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

The rule behind most design decisions here: **the LLM never touches the database directly, and never decides whose data it's looking up.** `tools_schema.py` defines every tool the model can call, and none accept a `user_id` — `get_recent_transactions` takes zero arguments, since the authenticated user is bound server-side from the JWT (`get_current_user`) before any tool runs. When the model picks a specific transaction (`resolve_transaction(transaction_id)`), that id is checked against `txn_by_id` — a dict built from the list *already fetched for that user* — never a fresh, unscoped query; an unrecognized or injected id just falls back to the safe selection list, never a database hit. Every LLM call only ever sees a small, pre-fetched, already-authorized slice of data (a few retrieved articles, or one transaction record) and is told to answer only from it.

**Two decision points, six tool schemas.** Call 1 (`tool_choice="auto"`) picks `search_knowledge_base` vs `get_recent_transactions` — intent routing. Each branch then forces a second tool choice rather than letting the model reply in plain text: the KB branch picks `answer_from_kb` vs `insufficient_kb_info`, the transaction branch picks `resolve_transaction` vs `no_single_match`. This pattern exists because an earlier version let the model "just reply" when unsure, and it would narrate the whole transaction list back as Markdown prose instead of using the card UI. Forcing a tool choice means the model's only way to communicate is a shape the server already validates — fixed UI-facing strings (`"Here are your recent transactions:"`, etc.) are chosen by the server, never written by the model. Every response is a `{type, message, data}` shape (`schemas/chat.py`); the frontend switches on `type` and never parses prose to figure out what happened.

### Embeddings and knowledge-base retrieval

An embedding is a 1536-number vector (OpenAI `text-embedding-3-small`) where semantically similar text lands close together, measured by cosine similarity. At seed time each FAQ's **question text** is embedded into a `pgvector` column; at query time the customer's raw message is embedded the same way and matched with `ORDER BY embedding <=> :query LIMIT 8` — no separate vector database.

Retrieval used to gate everything on one number: below a similarity threshold, decline; above it, answer. That broke on compound questions — "do I need to pay extra if I purchase gold?" scored *higher* against "How do I buy gold?" than against "What fees do you charge?" (the actually-relevant article), because "purchase gold" dominated the embedding over the weaker "pay extra" signal — so the real answer never even made the top-3 candidates. Fixed by decoupling retrieval from relevance: `kb_min_similarity` (0.30) is now just a noise floor for the candidate pool, widened to top 8; a forced tool choice (`answer_from_kb` / `insufficient_kb_info`) then has the model judge relevance from the actual article content, not a raw score. A real bonus of this: a previously-unsolved case ("Is my gold insured against theft?", which scored 0.637 — just under the old 0.65 cutoff) now resolves correctly too, since the model can tell the "Is my investment insured?" article answers it even though the wording differs.

Two earlier bugs in how articles get embedded, also worth noting: embedding `question + answer` combined diluted the vector enough that an exact-match question scored only 0.74 against itself (fixed by embedding the question alone → 1.0); and letting the model rephrase the query before embedding hurt more than it helped (measured with `scripts/eval_kb.py`, an 11-query standing eval) — "How can I exchange my gold for cash?" → "how to exchange gold for cash" dropped a genuine match from 0.799 to 0.733 (fixed by always embedding the customer's raw message). No ANN index (HNSW/IVFFlat) yet — brute-force is simpler and fast enough at ~18 articles.

### Conversations, sessions, and why the backend stays stateless

The backend keeps no server-side session — every `POST /chat` gets `message` + a trimmed `history` and forgets it immediately after responding. The **conversation id lives in the URL** (`?c=<uuid>`, minted on login or "New chat"); the frontend keeps messages in React state, mirrors them to `sessionStorage` keyed by `(userId, conversationId)`, and sends the last 10 turns back as history — including the actual transaction records shown earlier, not just the reply text, so a later "the second one" still resolves correctly. Trade-off: conversations don't survive a device switch — the first thing to change for production (see below).

## Testing

```bash
cd backend && pytest
```

17 tests, all deterministic and offline (every OpenAI call is monkeypatched at the `llm_client` seam — no network access or API key needed). The two highest-value ones:

- **`test_transaction_authz.py`** — user A's JWT can fetch their own transaction (200) but never user B's (404), and `/transactions/recent` never returns another user's rows. This is the literal trust boundary described above, under test.
- **`test_kb_grounding.py`** — asserts the below-threshold path returns `grounded: false` *and* that the second ("write the grounded answer") LLM call is never invoked in that case — the no-hallucination guard is tested as a structural fact, not just a prompt.

## What I would improve for production

- **Security**: replace the no-password mock login with real authentication; add rate limiting on `/chat` (each call can trigger 1–3 OpenAI requests); add request size limits and stricter CORS in production.
- **Observability**: per-`conversation_id` JSONL logging with per-call token/cost tracking exists (`backend/app/services/session_log.py`) and a coverage eval script (`scripts/eval_faq_coverage.py`) reports KB grounding rate across a 180-question fixture — but it's file-based and run by hand, not wired into a real dashboard, alerting, or latency tracing yet.
- **Scalability**: persist conversations server-side (Postgres or Redis) instead of trimmed client-sent history, so a conversation survives a device switch and doesn't grow unbounded on the client; add an HNSW index on `support_articles.embedding` once the KB is large enough that brute-force search matters.
- **Retrieval quality**: chunk longer articles instead of one-embedding-per-FAQ, add reranking over the candidate pool for large knowledge bases (fine to skip at ~18 articles, matters once it's hundreds), and surface citations in the UI (the backend already returns `sources`, the frontend doesn't show them yet).
- **Cost**: cache embeddings for repeated/similar queries; consider a cheaper/faster model for the intent-routing and resolve steps versus the final answer-generation step.
- **Escalation**: a "hand off to a human agent" action when the KB has no grounded answer twice in a row, or when a transaction explanation can't be generated — right now the fallback message just apologizes.
