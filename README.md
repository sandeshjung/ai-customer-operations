# AI Customer Operations

An event-driven AI customer operations platform that autonomously detects
business issues, investigates them using tools and RAG, makes decisions,
and escalates high-risk cases to human operators.

## Core Workflows

1. Proactive Delayed-Order Agent
2. AI Support Ticket Triage Agent
3. Resolution Agent

## Technology

- Python
- FastAPI
- PostgreSQL
- Redis
- Qdrant
- LangGraph
- RAG
- LLM tool calling
- Docker
- AWS
- OpenTelemetry
- Langfuse

## Development

### Start infrastructure

```bash
docker compose up -d
```

### Start API
```bash
make dev
```

### Run tests
```bash
make test
```

