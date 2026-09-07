import json
from typing import Any

from app.rag.retriever import search_policy


def reciprocal_rank(results: list[dict[str, Any]], expected_sources: set[str]) -> float:
    for rank, result in enumerate(results, start=1):
        # Gracefully handle malformed results
        if result.get("source") in expected_sources:
            return 1.0 / rank
    return 0.0


def evaluate():
    with open("backend/evaluation/datasets/rag_questions.json", encoding="utf-8") as file:
        dataset = json.load(file)

    correct = 0
    total_mrr = 0.0

    for item in dataset:
        results = search_policy(item["question"], limit=5)
        total_mrr += reciprocal_rank(results, set(item["expected_sources"]))
        retrieved_sources = {result["source"] for result in results}
        expected_sources = set(item["expected_sources"])
        hit = bool(retrieved_sources & expected_sources)

        if hit:
            correct += 1

        print(f"Question: {item['question']}")
        print(f"Expected: {expected_sources}")
        print(f"Retrieved: {retrieved_sources}")
        print(f"Hit: {hit}")
        print("-" * 60)

    recall_at_5 = correct / len(dataset) if dataset else 0
    mrr = total_mrr / len(dataset) if dataset else 0.0

    print(f"Recall@5: {recall_at_5:.2%}")
    print(f"MRR: {mrr:.3f}")

    # ADD THIS RETURN STATEMENT
    return {
        "recall_at_5": recall_at_5,
        "mrr": mrr,
    }


if __name__ == "__main__":
    evaluate()