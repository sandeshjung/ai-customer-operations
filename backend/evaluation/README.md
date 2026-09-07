# Evaluation Framework

Measures the delayed-order agent, the ticket triage agent, and the RAG
retrieval pipeline against small hand-labeled datasets in `datasets/`.

## Running

```bash
make evaluate            # full run, writes a report to reports/
make evaluate-quick       # first 3 scenarios of each dataset only (smoke test)
make evaluate-reset       # clear checkpoints, next run starts fresh
```

Reports land in `backend/evaluation/reports/eval_run-<timestamp>.json`
(and `eval_run-latest.json`).

## Working within a free-tier LLM budget

The agent evaluations call a real LLM per scenario (the delayed-order
agent can make several calls per scenario, since it loops through tool
calls before producing a decision). On a rate-limited free tier
(e.g. Groq), running the full dataset can hit 429s well before finishing
— so the scripts are built to survive that instead of crashing:

- **Pacing** — a delay between scenarios (`EVAL_SLEEP_SECONDS`, default 5s).
- **Backoff** — on a 429, the specific call is retried with exponential
  backoff (`EVAL_MAX_RETRIES`, default 4; `EVAL_BACKOFF_SECONDS`, default 20)
  instead of aborting the whole run.
- **Checkpointing** — every completed scenario is appended to
  `reports/<name>.checkpoint.jsonl`. If the run is killed (e.g. daily quota
  exhausted), re-running skips scenarios already recorded and only spends
  calls on what's left. Run `make evaluate-reset` to force a clean re-run.
- **EVAL_LIMIT** — cap how many scenarios run, for a cheap smoke test:
  `EVAL_LIMIT=3 make evaluate`.

The RAG retrieval eval (`recall@5`, `MRR`, `context relevance`) makes
**zero** LLM calls — it only uses the local embedding model — so run it as
often as you like.

## Faithfulness (optional, costs LLM calls)

`retrieval/evaluate_faithfulness.py` asks the LLM to answer each RAG
question from retrieved context and self-report whether the answer is
grounded in it. This is a real quality signal but doubles the LLM budget
of the RAG eval, so it's opt-in:

```bash
RUN_FAITHFULNESS=1 make evaluate
```

## Dataset sizes

Currently 15 delayed-order scenarios, 15 triage scenarios, and 12 RAG
questions — enough to cover every enum value (all severities, all
resolutions, all ticket intents/sentiments/actions) without burning
through a free-tier quota. Treat the `run_all.py` gate thresholds as
smoke-test gates, not statistically rigorous benchmarks, at this sample
size. Scale the datasets up in `datasets/*.json` once you're on a paid
tier or a locally-hosted model.
