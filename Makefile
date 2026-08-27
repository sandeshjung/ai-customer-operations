install:
	uv sync

dev:
	uv run uvicorn app.main:app --app-dir backend --reload

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

infra-up:
	docker compose up -d

infra-down:
	docker compose down

infra-logs:
	docker compose logs -f

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest

seed:
	PYTHONPATH=backend uv run python backend/scripts/seed_database.py