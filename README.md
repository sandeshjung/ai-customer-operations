# AI Customer Operations

An event-driven AI customer operations platform. Two LLM agents monitor
delayed orders and triage support tickets, decide what to do, and either
act automatically or queue the decision for human approval. Built as a
portfolio project demonstrating production-grade agent patterns:
tool-calling, RAG, human-in-the-loop, observability, and the operational
bugs that show up once you actually build this stuff (races, idempotency,
prompt injection, Docker cold-start reliability) rather than just the
happy path.

**Core flow:** `ORDER_DELAYED` event → Delayed Order Agent investigates
(tool calls + RAG over the shipping policy) → decision → auto-executed or
queued for human approval → if it creates a ticket, `TICKET_CREATED` event
→ Triage Agent classifies it → optionally, a customer notification.

## What's included

- **Backend API** (FastAPI) + **worker** (LangGraph agents, Redis Streams consumer)
- **Admin console** (`frontend/admin`) — approvals, delayed orders, tickets, sent notifications
- **Customer portal** (`frontend/customer`) — read-only guest order lookup (order ID + email)
- Postgres, Redis, Qdrant, Jaeger for tracing

## Tech stack

Python 3.12, FastAPI, PostgreSQL, Redis (event bus + rate limiting + idempotency),
Qdrant (vector store), LangGraph, Groq (LLM provider), OpenTelemetry + Jaeger,
React + Vite, Docker Compose, uv, Alembic, pytest.

Swapping the OTel exporter to Langfuse is a two-env-var change (no code changes) —
see `CLAUDE.md`'s Observability section. Not configured by default.

## Getting started (from a fresh clone)

### Prerequisites

- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python dependency manager)
- Node.js 20+
- A [Groq API key](https://console.groq.com/keys) (free tier works, see rate-limit notes in `CLAUDE.md`)

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:
- `LLM_API_KEY` — your Groq key
- `ADMIN_API_KEY` — any string you choose; it gates all admin/mutating endpoints (`.env.example` doesn't list this yet — add it yourself)

Everything else has a working local default.

### 2. Start the stack

```bash
docker compose up -d
```

This starts Postgres, Redis, Qdrant, Jaeger, the API, the worker, an
autoheal watchdog for the worker, and both frontends (built and served via
nginx). First start takes longer — the worker downloads an embedding model
and, if the Qdrant collection is empty, runs the knowledge-base ingestion
automatically.

Check everything is up:

```bash
docker compose ps
curl http://localhost:8000/health
```

### 3. Run migrations and seed data

The `api` container runs migrations automatically on start. To do it
manually (or if running the API outside Docker):

```bash
PYTHONPATH=backend uv run alembic upgrade head
```

Seed synthetic customers, orders, shipments, and products:

```bash
make seed
```

### 4. Use it

| App | URL |
|---|---|
| Admin console | http://localhost:8080 (or `cd frontend/admin && npm install && npm run dev` → http://localhost:5173) |
| Customer portal | http://localhost:8081 (or `cd frontend/customer && npm install && npm run dev` → http://localhost:5174) |
| API | http://localhost:8000 (docs at `/docs`) |
| Jaeger (traces) | http://localhost:16686 |

The admin console needs the `ADMIN_API_KEY` from step 1, entered into its
header field — it's stored in your browser's `localStorage`, not baked in.

To see the agents actually do something: in the admin console's "Delayed
orders" panel, use "Publish N to event stream" (small N — each one costs a
real LLM call and is paced ~5s apart) and watch approvals/tickets/
notifications appear live.

### 5. Run tests

```bash
make test
# or, narrower:
uv run pytest backend/tests/services/
```

Four test files need real network access to HuggingFace (embedding model
download) and a populated Qdrant collection — see `CLAUDE.md`'s testing
conventions for which ones and why they're excluded from CI.

## Local development without Docker for the backend

```bash
uv sync
docker compose up -d postgres redis qdrant jaeger   # infra only
PYTHONPATH=backend uv run alembic upgrade head
make seed
make dev                                             # API with --reload
PYTHONPATH=backend uv run python backend/scripts/run_worker.py   # separate terminal
```

## More detail

`CLAUDE.md` documents the non-obvious parts of this codebase in depth —
import-time side effects, idempotency patterns, Docker/worker reliability
gotchas, and known gaps. Worth reading before making changes.

## License

MIT — see [LICENSE](LICENSE).
