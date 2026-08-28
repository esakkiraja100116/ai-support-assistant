# Backend

FastAPI service for the support assistant: chat orchestration, knowledge-base retrieval (pgvector), and authorized transaction lookups.

## Setup

```bash
# from repo root
docker compose up -d db

cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set OPENAI_API_KEY, and generate a real JWT_SECRET, e.g.:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

alembic upgrade head
python -m scripts.seed   # requires OPENAI_API_KEY (embeds the FAQ articles)
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs

## Test

```bash
pytest
```

Tests run against a real local Postgres (a `_test`-suffixed database is created automatically) because pgvector's similarity search needs the real extension. All OpenAI calls are monkeypatched at the `app.services.llm_client` seam — no network calls or API key needed to run the suite.

## Architecture

See the root [README](../README.md#architecture) for the full request-flow walkthrough (tool-calling, embeddings, the trust boundary). Short version:

- `app/models.py` — `User`, `Transaction`, `SupportArticle` (with a `pgvector` embedding column).
- `app/auth/` — mock login issues a signed JWT (`sub=user_id`, no password); `get_current_user` is a FastAPI dependency every protected route uses. Transaction lookups only ever filter by the JWT's `user_id` — never a client- or model-supplied id.
- `app/services/llm_client.py` — the only module that talks to the OpenAI SDK. Tests monkeypatch this module directly.
- `app/services/tools_schema.py` — every tool schema and the system prompt, in one place. None of them accept a user-id parameter, so the model can never supply or leak one.
- `app/services/orchestrator.py` — the whole `POST /chat` decision tree: intent routing, knowledge-base grounding + threshold guard, and the transaction resolve-or-list step.
- `scripts/seed.py` — idempotent (truncate + reinsert) seed of 2 users, 7 transactions each across all type/status combinations, and 18 FAQ articles, embedded on their **question text only** (see root README's embeddings section for why).
- `scripts/eval_kb.py` — a small standing retrieval eval (`python -m scripts.eval_kb`), not part of `pytest`. Run it by hand after touching anything in the KB retrieval path (embedding input, threshold, seed content) — it's what caught the query-rephrasing regression documented in the root README.

## Trade-offs / what I'd change for production

See the root [README](../README.md#what-i-would-improve-for-production).
