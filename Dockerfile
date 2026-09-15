FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY backend/ backend/
COPY data/ data/
COPY docs/ docs/
COPY alembic.ini README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/backend"
# stdout isn't a TTY in a container, so Python block-buffers it by default —
# print() calls (event_consumer.py's progress lines) can sit unflushed
# indefinitely, making a perfectly healthy worker look stuck in `docker logs`.
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]