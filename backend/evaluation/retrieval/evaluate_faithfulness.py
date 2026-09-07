"""
Optional faithfulness evaluation for the RAG pipeline.

Unlike evaluate_retrieval.py (recall@5 / MRR / context relevance, which are
free — embeddings only), this one asks the LLM to answer each question from
the retrieved context and self-report whether the answer is fully grounded
in it. That's one extra LLM call per question, so it's kept separate and
opt-in rather than bundled into every run_all.py execution.

Run standalone:
    PYTHONPATH=backend uv run python backend/evaluation/retrieval/evaluate_faithfulness.py

Or opt into it from run_all.py:
    RUN_FAITHFULNESS=1 make evaluate
"""

import json
from pathlib import Path

from app.ai.client import client
from app.core.config import settings
from evaluation.utils import apply_eval_limit, paced_sleep, retry_with_backoff

DATASET_PATH = Path("backend/evaluation/datasets/rag_questions.json")

JUDGE_PROMPT = """You will answer a question using ONLY the context provided below.

Context:
{context}

Question: {question}

Respond with ONLY valid JSON, no markdown, no extra text:
{{
  "answer": "your answer using only the context above",
  "faithfulness_score": 0.0-1.0,
  "faithfulness_reasoning": "one short sentence on whether the answer is fully supported by the context"
}}

faithfulness_score should be 1.0 only if every claim in your answer is
directly supported by the context, and 0.0 if you had to rely on outside
knowledge because the context didn't contain the answer.
"""


def _judge(question: str, context: str) -> dict:
    def _call():
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": JUDGE_PROMPT.format(context=context, question=question),
                }
            ],
        )
        content = response.choices[0].message.content
        return json.loads(content)

    return retry_with_backoff(_call, description=f"faithfulness judge: {question[:40]}")


def evaluate_faithfulness():
    from app.rag.service import retrieve_policy

    with open(DATASET_PATH, encoding="utf-8") as f:
        dataset = apply_eval_limit(json.load(f))

    total_score = 0.0
    completed = 0
    failed = []

    for item in dataset:
        chunks = retrieve_policy(item["question"], limit=3)
        context = "\n\n".join(c["content"] for c in chunks)

        if not context.strip():
            print(f"Question: {item['question']}\n  No context retrieved, skipping.")
            print("-" * 60)
            continue

        try:
            result = _judge(item["question"], context)
        except Exception as exc:
            print(f"FAIL | {item['question']}: {exc}")
            failed.append({"question": item["question"], "error": str(exc)})
            paced_sleep()
            continue

        score = float(result.get("faithfulness_score", 0.0))
        total_score += score
        completed += 1

        print(f"Question: {item['question']}")
        print(f"  Answer: {result.get('answer', '')[:150]}")
        print(f"  Faithfulness: {score:.2f} — {result.get('faithfulness_reasoning', '')}")
        print("-" * 60)
        paced_sleep()

    total = completed or 1
    faithfulness = total_score / total

    print(f"\nCompleted: {completed}/{len(dataset)} (failed: {len(failed)})")
    print(f"Average Faithfulness: {faithfulness:.2%}")

    return {
        "total_scenarios": len(dataset),
        "completed": completed,
        "failed": failed,
        "faithfulness": faithfulness,
    }


if __name__ == "__main__":
    evaluate_faithfulness()
