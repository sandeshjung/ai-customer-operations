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


.PHONY: evaluate evaluate-quick evaluate-reset
evaluate:
	PYTHONPATH=backend uv run python backend/evaluation/run_all.py

# Smoke test with only the first 3 scenarios of each dataset — use this
# first to confirm everything is wired up before spending a full run's
# worth of free-tier LLM calls.
evaluate-quick:
	PYTHONPATH=backend EVAL_LIMIT=3 uv run python backend/evaluation/run_all.py

# Clear checkpoints so the next run re-evaluates every scenario from
# scratch instead of resuming.
evaluate-reset:
	rm -f backend/evaluation/reports/*.checkpoint.jsonl