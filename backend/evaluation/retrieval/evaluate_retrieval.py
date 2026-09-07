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
    """Retrieval-only evaluation: recall@5, MRR, and context relevance.

    Deliberately makes zero LLM calls — it only exercises the embedding
    model (local HuggingFace model) and Qdrant, so it's free to run as
    often as you like even on a rate-limited LLM free tier. Faithfulness
    (which needs an LLM to judge groundedness) lives in a separate,
    opt-in script — see evaluate_faithfulness.py.
    """
    with open("backend/evaluation/datasets/rag_questions.json", encoding="utf-8") as file:
        dataset = json.load(file)

    correct = 0
    total_mrr = 0.0
    total_relevance = 0.0

    for item in dataset:
        # Use the raw vector search (not the hybrid/BM25 blend) here since
        # we want the actual cosine similarity scores for context relevance,
        # not a fused rank.
        results = search_policy(item["question"], limit=5)
        total_mrr += reciprocal_rank(results, set(item["expected_sources"]))
        retrieved_sources = {result["source"] for result in results}
        expected_sources = set(item["expected_sources"])
        hit = bool(retrieved_sources & expected_sources)

        if hit:
            correct += 1

        # Context relevance: how similar the retrieved chunks are to the
        # query, on average. A cheap, LLM-free proxy for "did we actually
        # retrieve relevant context" — high recall with low relevance
        # scores usually means the similarity threshold is too loose.
        scores = [r["score"] for r in results if r.get("score") is not None]
        relevance = sum(scores) / len(scores) if scores else 0.0
        total_relevance += relevance

        print(f"Question: {item['question']}")
        print(f"Expected: {expected_sources}")
        print(f"Retrieved: {retrieved_sources}")
        print(f"Hit: {hit} | Avg similarity: {relevance:.3f}")
        print("-" * 60)

    total = len(dataset) or 1
    recall_at_5 = correct / total
    mrr = total_mrr / total
    context_relevance = total_relevance / total

    print(f"Recall@5: {recall_at_5:.2%}")
    print(f"MRR: {mrr:.3f}")
    print(f"Context Relevance (avg similarity): {context_relevance:.3f}")

    return {
        "recall_at_5": recall_at_5,
        "mrr": mrr,
        "context_relevance": context_relevance,
    }


if __name__ == "__main__":
    evaluate()
