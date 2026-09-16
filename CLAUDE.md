# CLAUDE.md

Context for Claude Code working in this repo. Read this before making changes — several things here are non-obvious and will cost you time (or cause a wrong fix) if missed.

## What this is

An event-driven AI customer operations platform. Two LLM agents monitor delayed orders and triage support tickets, decide what to do, and either act automatically or queue the decision for human approval. Built as a portfolio project demonstrating production-grade agent patterns: tool-calling, RAG, human-in-the-loop, observability, evaluation, and the operational bugs that show up once you actually build this stuff (races, idempotency, prompt injection) rather than just the happy path.

Core flow: `ORDER_DELAYED` event → Delayed Order Agent investigates (tool calls: get_order, get_shipment, get_customer, search_shipping_policy) → decision → either auto-executed or queued for human approval → if it creates a ticket, `TICKET_CREATED` event → Triage Agent classifies it.

## Stack

Python 3.12+, FastAPI, PostgreSQL, Redis (event bus + rate limiting + idempotency), Qdrant (vector store), LangGraph (both agents), Groq (LLM provider), OpenTelemetry + Jaeger (tracing), React + Vite (admin console + customer portal), uv (dependency management), Alembic (migrations), pytest, Docker Compose.


## Directory structure

\```
backend/
  app/
    agents/
      graphs/          # delayed_order.py, triage_agent.py — the two LangGraph agents
      tools/            # DB-backed tools the delayed-order agent calls
      models.py         # AgentDecision, TriageDecision (pydantic, not DB models)
      guardrails.py      # post-decision validation (e.g. CRITICAL severity forces requires_human)
    api/                # FastAPI routers — one file per resource, incl. customer_portal.py
    core/
      config.py          # Settings (pydantic-settings, reads .env)
      security.py         # require_api_key, rate_limit dependencies
      tracing.py           # OpenTelemetry setup + helpers (traced, inject/extract/link)
      pricing.py            # Groq $/token table + estimate_cost_usd — used by the AI usage
                             # monitor (GET /admin/usage), not real billing
      database.py, redis.py, logging.py
    events/              # Event schema, publisher, idempotency (atomic Redis claim), dead-letter
    models/              # SQLAlchemy models
    rag/                  # hybrid (BM25 + vector) retrieval over policy docs
    schemas/              # pydantic request/response schemas for the API
    services/             # business logic — agent_service, triage_service, action_service,
                           # approval_service, notification_service (see Mailjet note below)
    workers/
      event_consumer.py     # the Redis Streams polling loop — see gotchas below
      health.py              # liveness HTTP server + Redis heartbeat, used by the worker's
                              # Docker healthcheck and the autoheal container
  alembic/versions/       # migrations
  evaluation/              # agent accuracy eval harness, scaled for Groq free-tier limits
  scripts/                 # seed_database.py, run_worker.py, ingest_knowledge.py, start_worker.sh
  tests/
frontend/admin/            # React admin console (note the typo — see above) — approvals,
                            # delayed orders, tickets, notifications, dark ops-console UI
frontend/customer/          # React customer portal — guest order lookup (order ID + email,
                            # not real auth), read-only, light UI deliberately distinct from admin
data/knowledge/             # policy PDFs, embedded into Qdrant
docs/                        # plain-text source of the same policy docs (used for chunking/ingestion)
Dockerfile                    # backend image, used by both the api and worker services below
docker-compose.yml              # full stack: Postgres, Redis, Qdrant, Jaeger, api, worker,
                                 # autoheal (restarts the worker if its healthcheck fails),
                                 # admin-console, customer-portal
\```

## Commands

\```bash
uv sync                                    # install deps
docker compose up -d                        # start the FULL stack: infra + api + worker + both frontends
                                             # (see README.md for the from-scratch setup walkthrough)
PYTHONPATH=backend uv run alembic upgrade head   # run migrations (only needed if not using docker compose's api service, which runs this itself)
make seed                                     # seed synthetic data
make dev                                       # start the API locally (uvicorn --reload) instead of in Docker
PYTHONPATH=backend uv run python backend/scripts/run_worker.py   # start the event worker locally (separate process)

make test                                      # full test suite
uv run pytest backend/tests/services/            # just the service layer
uv run pytest backend/tests/services/test_approval_service_concurrency.py -v   # the real threaded race test

make evaluate-quick                             # agent eval, first 3 scenarios only (cheap smoke test)
make evaluate                                    # full agent eval — costs real LLM calls, see below

cd frontend/admin && npm install && npm run dev    # admin console dev server, expects API at localhost:8000
cd frontend/customer && npm install && npm run dev  # customer portal dev server, same API
\```

Running `api`/`worker` via `docker compose` and via `make dev`/the local script at the same time will
fight over the same port — pick one or the other, not both.

pytest's `pythonpath` is already set to `backend` in `pyproject.toml`, so you usually don't need `PYTHONPATH=backend` for test runs — only for one-off scripts run directly.

## Non-obvious things that will bite you

**1. Importing the RAG chain triggers a real network call.** `app.rag.retriever` instantiates a real HuggingFace embedding model *at module import time*, unconditionally — no lazy loading. This chain gets pulled in transitively by almost anything agent-related: `agent_service` → `delayed_order` graph → `rag.service`. If you're writing a test or script that doesn't need real RAG, you must stub `sys.modules["app.rag.service"]` with a fake module **before** importing anything that touches it — patching it after import is too late, and `unittest.mock.patch("app.rag.service.x", ...)` itself triggers the real import while resolving the patch target. Look at `backend/tests/workers/test_event_consumer.py` or `test_triage_service.py` for the pattern (`sys.modules["app.rag.service"] = fake_module`, done at the very top of the file, before other imports).

**2. `TicketPriority` is stored as a plain `String(30)` column, not a real SQL enum.** Every fresh load from the DB returns a plain Python `str`, not a `TicketPriority` instance — even though the model's type hint says `Mapped[TicketPriority]`. The hint doesn't cause runtime coercion. If you need to compare or rank priorities, normalize first: `TicketPriority(db_ticket.priority)`. This bit us once already (`triage_service.py`'s priority-upgrade logic crashed on every real run until fixed) — don't assume `.value` or enum methods work on a value pulled fresh from the DB without normalizing.

**3. `event_consumer.py`'s `consume_events()` sleeps twice per message, always.** `time.sleep(15)` then `time.sleep(PROCESSING_DELAY_SECONDS)` (also 15) — 30s of dead time per event regardless of outcome, capping throughput at ~2 events/min. This is almost certainly meant as one Groq-rate-limit safeguard that got duplicated, not two intentional delays, but it hasn't been touched — see `TestSleepBehavior` in `test_consume_events.py` for the reasoning. Don't silently "fix" this; it's a deliberate choice to leave it for a human to decide on, not an oversight.

**4. Event processing uses atomic claims, not read-then-write, for idempotency and approval concurrency.** `try_claim_event()` (Redis `SET NX`) guards against two consumers processing the same event; `_claim_approval()` (SQL `UPDATE ... WHERE status = 'PENDING'`, checked via rowcount) guards against double-approving. If you're touching either of these, preserve the atomic-claim pattern — a plain "check status, then write" reintroduces a real race (there's a threaded test, `test_approval_service_concurrency.py`, that will catch it if you regress this).

**5. Groq free-tier rate limits shape a lot of design choices here.** The evaluation harness (`backend/evaluation/`) has retry/backoff/checkpointing and an `EVAL_LIMIT` env var specifically because running the full eval suite can blow through free-tier quota. Don't casually scale up dataset sizes or remove the pacing without checking `backend/evaluation/README.md`.

**6. `api`, `worker`, `admin-console`, and `customer-portal` all run as Docker containers, and Docker images are snapshots — they do NOT hot-reload source changes.** Editing a `.py` or frontend file and expecting the running container to pick it up will silently fail: you have to `docker compose up -d --build <service>` to rebuild. This bit us repeatedly in practice — e.g. toggling the Mailjet demo line in `notification_service.py` (see gotcha below) had zero effect until the container was rebuilt, and it's easy to end up with `api` and `worker` running two different versions of the same file if you rebuild one and not the other. When in doubt, `docker exec <container> grep <symbol> /app/backend/...` to check what code the container is actually running before debugging further.

**7. Auth is a single shared secret, not per-user.** `ADMIN_API_KEY` gates all mutating endpoints and the whole `/admin/*` router, sent via `X-API-Key` header. There's no login/session system — don't assume `current_user`-style patterns exist anywhere. If `ADMIN_API_KEY` isn't set, protected endpoints fail closed with a 503 (not silently open). `.env.example` doesn't currently list it — don't assume its absence there means it's optional.

**8. `notification_service.send_notification()` has a real Mailjet backend, deliberately left commented out.** `_send_via_mailjet()` / `_demo_send_via_mailjet()` exist and work (see `MAILJET_*` settings), but the call site in `send_notification()` is commented by default — uncommenting it sends a real email using whatever's in `.env`. Always double check which state a running container actually has (gotcha #6) before assuming it's off.

**9. The worker's `start_worker.sh` checks Qdrant collection existence via a raw `QdrantClient`, not `app.rag.vector_store` — on purpose.** Importing `app.rag.vector_store` (or `app.rag.retriever`) loads a real HuggingFace embedding model at import time (gotcha #1). The pre-check used to import it just to answer a yes/no question, silently doubling every worker cold-start's cost. Don't reintroduce that import there.

**10. Token/cost usage (the admin console's "AI usage" section, `GET /admin/usage`) is read from Postgres (`agent_executions`), not from the OTel spans.** Every LLM call sets `llm.input_tokens`/`llm.output_tokens`/`llm.total_tokens` as span attributes (gotcha in Observability below), but spans only go to Jaeger — they're not queryable data. `AgentExecution` rows carry their own `input_tokens`/`output_tokens`/`total_tokens`/`llm_call_count`/`duration_ms`/`model` columns, populated separately by `agent_service.py`/`triage_service.py` from the same `response.usage_metadata` the span attributes come from. If you add a new LLM call site, you must accumulate its usage into both places independently — updating the span doesn't update the DB row and vice versa. For the delayed-order graph specifically, `agent_node` can run multiple times per graph invocation (the tool-call loop) plus once in `decision_node`, so usage is accumulated across calls via `_usage_delta()` (`delayed_order.py`) into running totals on `DelayedOrderState`, not just read from the last response — a naive "read the last LLM response's usage" implementation undercounts every run that used a tool.

## Testing conventions

- `backend/tests/conftest.py` provides a `db_session` fixture: fresh in-memory SQLite per test, not Postgres. All models use plain SQLAlchemy types (no JSONB/ARRAY), so this is a faithful stand-in for service-layer tests. Concurrency tests need a *shared* SQLite DB across threads instead (plain `sqlite:///:memory:` gives each connection its own isolated DB) — see `test_approval_service_concurrency.py` for the `StaticPool` pattern.
- External services (Redis, the LLM, RAG) are mocked at the service-layer boundary — tests exercise real business logic against a real (in-memory) DB, with only genuinely external calls faked out.
- When you fix a bug found via manual testing or code review, write the regression test *and verify it actually catches the bug* — temporarily reintroduce the old code and confirm the test fails, then restore the fix. Several bugs in this codebase were caught exactly this way (see git history for `reject()`'s missing return statement, or the triage priority-comparison bug).
- `backend/tests/agents/test_delayed_order.py`, `test_rag_integration.py`, and both files under `backend/tests/rag/` need real network access (HuggingFace) — expect these to fail in sandboxed/offline environments; that's a pre-existing environment limitation, not a code bug.

## Observability

OpenTelemetry traces everything: every tool call, every LLM call (with token usage), every RAG retrieval, one root span per agent run and per event processed. Default exporter is local Jaeger (`docker compose up -d jaeger`, UI at `localhost:16686`, zero signup). Swap to Langfuse by changing two env vars (`OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_EXPORTER_OTLP_HEADERS`) — no code changes needed, since Langfuse OSS 3.22+ ingests OTLP natively.

Trace context propagates across the async event boundary: when the delay agent's auto-execute path publishes `TICKET_CREATED`, it injects the current trace context into the event payload, and the consumer continues that same trace rather than starting a new one. The human-approval path is different — by the time someone clicks Approve, the original trace is long closed, so that path uses an OTel **Link** (a cross-trace reference) instead of a parent-child relationship. Don't conflate these two mechanisms; they solve different problems (live process boundary vs. temporally disjoint actions).

## Known gaps (not fixed, don't assume they are)

- `GET /tickets` and `GET /portal/orders/{id}` are intentionally public (no API key) — the customer portal needs them unauthenticated. The portal's order+email match is a guessing deterrent, not real security (see the comment in `customer_portal.py`).
- Rate limiting is fixed-window (not sliding-window/token-bucket) — good enough to stop accidental abuse, not a determined attacker.
- Prompt-injection mitigation on the triage agent (delimiting customer content, explicit system-prompt instruction) is real but unverified against an actual model — no automated test can confirm the LLM *obeys* the instruction without a paid API call. Treat it as a mitigation, not a guarantee.
- Neither frontend has automated tests (no Vitest/RTL) — verification so far has been manual/Playwright, not committed as regression coverage.
- CORS is permissive by default (`DEBUG=true` allows any localhost port). Set `DEBUG=false` and `CORS_ALLOWED_ORIGINS` (comma-separated) before any real deployment — see `main.py`.
- The AI usage monitor's cost estimates (`pricing.py`, `GET /admin/usage`) use a hardcoded `$/token` table that isn't kept in sync with Groq's actual pricing page, and cost is computed at read time from *current* rates, not the rate that was live when a given run actually happened — fine for a rough efficiency signal, not for real billing/reconciliation. Unpriced models return `cost_usd: null` (surfaced as `cost_incomplete: true`) rather than a silently wrong `$0`.


## Git
Never run `git commit` or `git push` unless explicitly asked in the current
message. Leave changes staged/unstaged for review.

### Make sure to be concise with all of your responses.