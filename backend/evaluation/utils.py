"""
Shared helpers for evaluation scripts.

These exist specifically to make evaluation runnable on a rate-limited
free-tier LLM provider (Groq):

- retry_with_backoff: retries a single LLM/graph call when a 429 /
  rate-limit error is hit, instead of crashing the whole run.
- paced_sleep: a small delay between scenarios so we don't hammer the
  provider's requests-per-minute limit.
- Checkpoint: append-as-you-go JSONL result log so a run that gets
  killed partway (e.g. daily quota exhausted) doesn't lose progress.
  Re-running the same script skips scenarios already recorded.

Env vars (all optional, sensible defaults for a free tier):
  EVAL_SLEEP_SECONDS   delay between scenarios            (default 5)
  EVAL_MAX_RETRIES     retries per scenario on rate limit  (default 4)
  EVAL_BACKOFF_SECONDS base backoff delay, doubles each retry (default 20)
  EVAL_LIMIT           only run the first N scenarios (default: all)
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

SLEEP_BETWEEN_SCENARIOS = float(os.getenv("EVAL_SLEEP_SECONDS", "5"))
MAX_RETRIES = int(os.getenv("EVAL_MAX_RETRIES", "4"))
BASE_BACKOFF_SECONDS = float(os.getenv("EVAL_BACKOFF_SECONDS", "20"))
EVAL_LIMIT = os.getenv("EVAL_LIMIT")

REPORTS_DIR = Path("backend/evaluation/reports")


def _is_rate_limit_error(exc: Exception) -> bool:
    """Best-effort detection across groq / langchain-groq exception types."""
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "rate_limit" in text or "429" in text


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    description: str,
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_BACKOFF_SECONDS,
) -> T:
    """Call fn(), retrying with exponential backoff only on rate-limit errors.

    Any other exception is raised immediately — we don't want to silently
    retry on real bugs (bad JSON, validation errors, etc.), only on
    "provider is throttling us" conditions.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt >= max_retries:
                raise
            delay = base_delay * (2**attempt)
            attempt += 1
            logger.warning(
                "Rate limited, backing off | task=%s attempt=%s/%s delay=%.0fs",
                description,
                attempt,
                max_retries,
                delay,
            )
            print(
                f"  [rate limited] {description} — retry {attempt}/{max_retries} "
                f"in {delay:.0f}s"
            )
            time.sleep(delay)


def paced_sleep() -> None:
    """Small delay between scenarios to stay under requests-per-minute limits."""
    if SLEEP_BETWEEN_SCENARIOS > 0:
        time.sleep(SLEEP_BETWEEN_SCENARIOS)


def apply_eval_limit(scenarios: list[dict]) -> list[dict]:
    """Optionally truncate a dataset via EVAL_LIMIT, for cheap smoke tests."""
    if EVAL_LIMIT:
        limit = int(EVAL_LIMIT)
        if limit < len(scenarios):
            print(f"EVAL_LIMIT={limit} set — running {limit}/{len(scenarios)} scenarios")
        return scenarios[:limit]
    return scenarios


class Checkpoint:
    """Append-only JSONL log of per-scenario results, keyed by scenario id.

    Lets an evaluation run resume after being interrupted (e.g. by hitting
    a daily token/request quota) without re-spending calls on scenarios
    that already completed successfully.
    """

    def __init__(self, name: str):
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self.path = REPORTS_DIR / f"{name}.checkpoint.jsonl"
        self._done: dict[str, dict] = {}
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    self._done[str(record["id"])] = record

    def get(self, scenario_id) -> dict | None:
        return self._done.get(str(scenario_id))

    def record(self, scenario_id, result: dict) -> None:
        entry = {"id": str(scenario_id), **result}
        self._done[str(scenario_id)] = entry
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def all_results(self) -> list[dict]:
        return list(self._done.values())

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()
        self._done = {}


def write_report(name: str, payload: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    path = REPORTS_DIR / f"{name}-{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    # Also keep a stable "latest" pointer so CI/tools don't need to glob.
    latest_path = REPORTS_DIR / f"{name}-latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return path
