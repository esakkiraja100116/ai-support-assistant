---
name: setup-repo
description: Bootstraps this repository for local development - starts Postgres (with pgvector), sets up the Python backend venv and .env, runs migrations, seeds the database, installs frontend dependencies, and starts both dev servers. Use when a new contributor asks to set up, bootstrap, or get this project running locally for the first time.
---

This repo is a full-stack support assistant: Next.js frontend + FastAPI backend + Postgres/pgvector + OpenAI. Follow these steps in order from the repo root. Report progress as you go rather than running everything silently and dumping output at the end.

## 1. Check prerequisites

Verify these are installed before starting; tell the user what's missing rather than failing partway through:

```bash
docker --version && docker compose version
python3 --version
node --version && npm --version
```

## 2. Start Postgres

```bash
docker compose up -d db
```

This starts `pgvector/pgvector:pg16` on host port **5433** (mapped from container 5432 — deliberately not 5432, to avoid colliding with a native Postgres install on the host, which is a real thing that happens). If this port is *also* taken on the user's machine, change the `ports:` mapping in `docker-compose.yml` and the port in `backend/.env`'s `DATABASE_URL` to match — don't just kill whatever else is using the port.

## 3. Backend setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

cp .env.example .env
```

Then fill in `backend/.env`:
- **`OPENAI_API_KEY`** — ask the user for a real key; the seed script and all chat/embedding calls need it. Never guess or fabricate one, and never print an existing key back to the user once you have it.
- **`JWT_SECRET`** — generate a real one, don't leave the placeholder:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

Run migrations and seed the database:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed
```

`scripts/seed.py` truncates and re-inserts, so it's safe to re-run. It makes real OpenAI embedding calls (one per FAQ article) — if it fails with an auth error, the API key is the first thing to check. Note it reads `OPENAI_API_KEY` from the actual process environment first and `.env` second (standard `pydantic-settings` precedence) — if the user already has a *different*, possibly stale, `OPENAI_API_KEY` exported in their shell, it will silently win over whatever you just wrote to `.env`. Check with `env | grep OPENAI_API_KEY` and unset it for these commands if so.

## 4. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/health` → `{"status":"ok"}`. Interactive docs at `http://localhost:8000/docs`.

## 5. Frontend setup

```bash
cd ../frontend
npm install
cp .env.example .env.local
```

`.env.local`'s `NEXT_PUBLIC_API_BASE_URL` defaults to `http://localhost:8000` — fine unless the backend is running somewhere else.

## 6. Start the frontend

```bash
npm run dev
```

Open `http://localhost:3000`. It should show a login screen listing the seeded accounts (Alice, Bob) from `GET /auth/users` — if that list is empty, the seed step didn't run or didn't succeed.

## 7. Verify it actually works

Don't declare success on server-up alone. Log in as one seeded user and confirm both core flows:
- A knowledge-base question (e.g. "How do I sell my gold?") returns a grounded answer.
- A transaction question (e.g. "show me my recent transactions") returns real seeded transaction data.

If either fails, check `backend/app/services/orchestrator.py`'s logs (uncaught exceptions are logged server-side, not shown to the client) before assuming the frontend is broken.

## Reference

Full architecture, the tool-calling/embeddings design, and troubleshooting notes live in the root [README.md](../../README.md), [backend/README.md](../../backend/README.md), and [frontend/README.md](../../frontend/README.md) — read those for *why* things are built this way, not just *how* to run them.
