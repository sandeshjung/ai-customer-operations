import json
from typing import Any

from app.rag.retriever import search_policy


def reciprocal_rank(results: list[dict[str, Any]], expected_sources: set[str]) -> float:
    for rank, result in enumerate(results, start=1):
        # Gracefully handle malformed results
        if result.get("source") in expected_sources:
            return 1.0 / rank
    return 0.0


def evaluate(dataset_path: str = "backend/evaluation/datasets/rag_questions.json") -> None:
    try:
        with open(dataset_path, encoding="utf-8") as file:
            dataset = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Failed to load dataset: {exc}")
        return

    if not dataset:
        print("Dataset is empty.")
        return

    correct = 0
    total_mrr = 0.0
    total_recall = 0.0

    for item in dataset:
        question = item.get("question")
        expected = set(item.get("expected_sources", []))

        if not question or not expected:
            print(f"Skipping invalid item: {item}")
            continue

        try:
            results = search_policy(question, limit=5)
        except Exception as exc:
            print(f"search_policy failed for '{question}': {exc}")
            continue

        total_mrr += reciprocal_rank(results, expected)

        retrieved = {r.get("source") for r in results if isinstance(r, dict)}
        hit = bool(retrieved & expected)
        if hit:
            correct += 1

        # True Recall@5
        recall = len(retrieved & expected) / len(expected)
        total_recall += recall

        print(f"Question: {question}")
        print(f"Expected: {expected}")
        print(f"Retrieved: {retrieved}")
        print(f"Hit: {hit}")
        # print(f"{results}")
        print("-" * 60)

    n = len(dataset)
    hit_rate_at_5 = correct / n
    mrr = total_mrr / n
    recall_at_5 = total_recall / n

    print(f"Hit Rate@5: {hit_rate_at_5:.2%}")
    print(f"Recall@5:  {recall_at_5:.2%}")
    print(f"MRR:       {mrr:.3f}")


if __name__ == "__main__":
    evaluate()