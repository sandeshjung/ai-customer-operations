# AI Customer Operations

An event-driven AI customer operations platform. Two LLM agents monitor
delayed orders and triage support tickets, decide what to do, and either
act automatically or queue the decision for human approval.

Built as a portfolio project to demonstrate production-grade agentic AI
patterns end to end — not just "call an LLM," but the surrounding system
a real deployment needs: tool-calling agents, retrieval-augmented
generation, prompt-injection resistance, human-in-the-loop guardrails,
event-driven idempotency, full observability, cost/usage accounting, and
an evaluation harness — plus the operational bugs that only show up once
you actually build this stuff (races, idempotency, Docker cold-start
reliability) rather than just the happy path.

## Architecture

![System architecture: Order Monitor publishes ORDER_DELAYED to Redis Streams; an Event Consumer worker routes it to the Delayed Order Agent or the Triage Agent; the Delayed Order Agent's decision passes through Guardrails into either a Human Approval Queue or auto-execution; both converge on an Action Service that creates a Support Ticket and Notification; escalated tickets re-enter Redis Streams as TICKET_CREATED; both agents share Postgres, a hybrid BM25+Qdrant RAG layer, and the Groq LLM; every call is traced to OpenTelemetry and every run's token usage is recorded for the admin console's AI usage monitor.](image/architecture.png)

**Core flow:** `ORDER_DELAYED` event → Delayed Order Agent investigates
(tool calls + hybrid RAG over the shipping policy) → decision → guardrails
check → auto-executed or queued for human approval → if it creates a
ticket, `TICKET_CREATED` event → Triage Agent classifies it → optionally,
a customer notification.

## What's included

- **Backend API** (FastAPI) + **worker** (LangGraph agents, Redis Streams consumer)
- **Admin console** (`frontend/admin`) — approvals, delayed orders, tickets, notifications, **AI usage/cost monitor**
- **Customer portal** (`frontend/customer`) — read-only guest order lookup (order ID + email)
- Postgres, Redis, Qdrant, Jaeger for tracing

## Techniques and concepts implemented

### Agentic tool use (LangGraph)

The Delayed Order Agent is a real tool-calling loop, not a single prompt:
it decides for itself which of `get_order`, `get_shipment`, `get_customer`,
and `search_shipping_policy` to call, over up to 5 iterations, before
producing a structured decision (severity, resolution, reasoning,
optional customer message). The Triage Agent is deliberately simpler —
one classification call per ticket — because ticket triage doesn't need
investigation, just judgment.

### Retrieval-augmented generation

Policy documents are retrieved with a **hybrid search**: BM25 (keyword)
and Qdrant vector (semantic) search run in parallel, then fused with
**Reciprocal Rank Fusion** (`score = Σ 1/(k + rank)`, k=60) rather than a
naive score blend, so a strong keyword match and a strong semantic match
both surface even when their raw scores aren't comparable. Retrieval
results are also cached in-process (LRU, 50 entries) on the normalized
query, visible as a `cache_hit` span attribute in traces.

The agent is instructed to retrieve policy before making a decision and
never invent policy content — decisions carry their supporting evidence
(source document, page, chunk index) so a reviewer can verify the claim
against the actual document, not just trust the model's summary.

### Prompt-injection resistance

The triage agent ingests raw customer-submitted text (ticket subject and
message) directly into its prompt — the classic injection surface. That
content is wrapped in `<customer_content>` delimiters with an explicit
system instruction to treat everything inside as data to classify, never
as commands, and to treat an embedded instruction *itself* as evidence of
a suspicious ticket rather than something to comply with. This is a
mitigation, not a guarantee — it hasn't been adversarially tested against
a live model, since that requires paid API calls to verify.

### Human-in-the-loop guardrails

Guardrails run *after* the LLM decides, not instead of it: if severity is
`CRITICAL` or the resolution is `ESCALATE`, `requires_human` is forced to
`true` regardless of what the model said — a code-level backstop the
model can't reason its way around. Decisions that require a human are
queued in an approval table rather than executed; approving or rejecting
is an atomic `UPDATE ... WHERE status = 'PENDING'` (checked via rowcount),
not a read-then-write, so two reviewers double-clicking the same approval
can't both win.

### Event-driven architecture and idempotency

Order-delay detection and ticket creation communicate via Redis Streams,
not direct calls, so the API, the worker, and the agents stay
independently deployable and restartable. Every event claim is atomic
(`SET NX` in Redis) so two consumer instances processing the same stream
can't double-handle one event. Events that fail processing go to a
dead-letter stream instead of being silently dropped or endlessly
retried.

### Observability

OpenTelemetry traces every tool call, every LLM call (with token usage as
span attributes), and every RAG retrieval, with one root span per agent
run and per event processed. Trace context is propagated across the
async event boundary: when an auto-executed decision publishes a
follow-up event, the trace context is injected into the event payload so
the consumer continues the *same* trace. The human-approval path is
different on purpose — by the time someone clicks Approve, the original
trace is long closed, so that path uses an OTel **Link** (a cross-trace
reference) instead of a parent-child relationship. Exports to Jaeger
locally by default; swapping to Langfuse is a two-environment-variable
change, since Langfuse OSS ingests OTLP natively.

### AI usage and cost monitoring

Token usage (input/output/total), LLM call count, and wall-clock duration
are recorded per agent run in Postgres — not just as trace data, since
traces are for debugging one run and this is for aggregating across all
of them. The delayed-order agent's tool-calling loop can make several LLM
calls per run, so usage is accumulated across every call in a single
graph invocation rather than read from just the last response, which
would silently undercount any run that used a tool. The admin console's
usage panel aggregates this into token/cost totals per agent and model,
plus a per-run breakdown with links back into Jaeger by trace ID. Cost is
estimated from a small `$/token` pricing table — a rough efficiency
signal, explicitly not billing-grade.

### Security

- **Auth**: a single shared API key (`X-API-Key`) gates all mutating and
  admin endpoints; missing configuration fails closed (503), not open.
- **Rate limiting**: fixed-window limits via Redis on sensitive endpoints
  (e.g. triggering delay detection) — enough to stop accidental abuse,
  not a determined attacker.
- **CORS**: environment-aware — permissive `localhost:*` only in debug
  mode, an explicit origin allowlist otherwise.
- **Scoped public surface**: the customer portal's endpoints (ticket
  list, order lookup) are intentionally unauthenticated, since a guest
  portal can't require an API key — order ID + email match is a guessing
  deterrent there, not real authentication, and that boundary is kept
  deliberately narrow rather than loosening auth elsewhere to match.

### Evaluation harness

The agents and the RAG pipeline are scored against small hand-labeled
datasets (15 delayed-order scenarios, 15 triage scenarios, 12 RAG
questions) — `recall@5` and `MRR` for retrieval quality, an optional LLM
faithfulness check (does the generated answer actually stay grounded in
the retrieved context, self-reported by the model), and decision-accuracy
scoring for both agents. Because this calls a real LLM per scenario
against a free-tier quota, the runner has pacing between scenarios,
exponential backoff on 429s, and checkpointing so a quota-exhausted run
resumes where it left off instead of restarting from scratch.

## Tech stack

Python 3.12, FastAPI, PostgreSQL, Redis (event bus + rate limiting +
idempotency), Qdrant (vector store) + BM25 (keyword search), LangGraph,
Groq (LLM provider, Llama 3.1), OpenTelemetry + Jaeger, React + Vite,
Docker Compose, uv, Alembic, pytest.

## Getting started (from a fresh clone)

### Prerequisites

- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python dependency manager)
- Node.js 20+
- A [Groq API key](https://console.groq.com/keys) (free tier works — see the evaluation harness above for why pacing/backoff matter)

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
notifications/AI usage appear live.

### 5. Run tests

```bash
make test
# or, narrower:
uv run pytest backend/tests/services/
```

A handful of test files need real network access (HuggingFace embedding
model download) and a populated Qdrant collection, and are expected to
fail in a sandboxed/offline environment — that's an environment
limitation, not a code bug.

```bash
make evaluate-quick   # agent + RAG eval, first 3 scenarios only (cheap smoke test)
make evaluate          # full evaluation run — costs real LLM calls
```

## Local development without Docker for the backend

```bash
uv sync
docker compose up -d postgres redis qdrant jaeger   # infra only
PYTHONPATH=backend uv run alembic upgrade head
make seed
make dev                                             # API with --reload
PYTHONPATH=backend uv run python backend/scripts/run_worker.py   # separate terminal
```

## Design notes and known limitations

- Prompt-injection mitigation is a real, tested-in-code defense but is
  unverified against an actual model in an automated way — confirming an
  LLM *obeys* the delimiting instruction requires a live, paid API call.
- Rate limiting is fixed-window, not sliding-window/token-bucket — enough
  to stop accidental abuse, not a determined attacker.
- AI usage cost estimates use a hardcoded, occasionally-stale `$/token`
  table and compute cost at read time from current rates, not the rate
  that was live when a run happened — a rough efficiency signal, not a
  billing reconciliation tool.
- Neither frontend has automated tests (no Vitest/RTL) yet — verification
  so far has been manual and Playwright-driven, not committed as
  regression coverage.
- Evaluation datasets are intentionally small (12–15 scenarios each) to
  stay inside a free-tier LLM quota — treat the pass/fail gates as
  smoke tests, not statistically rigorous benchmarks.

## License

MIT — see [LICENSE](LICENSE).
