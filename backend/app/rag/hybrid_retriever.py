from collections import defaultdict

from app.rag.retriever import search_policy as vector_search
from app.rag.bm25 import BM25Retriever
from app.rag.loader import load_documents
from app.rag.chunker import chunk_documents

K = 60

_documents = load_documents()
_chunks = chunk_documents(_documents)
bm25 = BM25Retriever(_chunks)

def _normalize_bm25_result(chunk: dict) -> dict:
    return {
        "content": chunk["text"],
        "source": chunk["source"],
        "page": chunk.get("page"),
        "chunk_index": chunk.get("chunk_index"),
        "version": "1.0",
        "score": None
    }

def _compute_rrf_scores(vector_results: list[dict], bm25_results: list[dict]) -> dict:
    """
    score = 1 / (k + rank) for each retriever, where k is a constant (here, 60) and rank is the position of the result in the list (starting from 0).
    """
    scores = defaultdict(float)

    # vector search score (rank 1 = best)
    for rank, result in enumerate(vector_results, start=1):
        key = (result.get("source"), result.get("chunk_index"))
        scores[key] += 1.0 / (K + rank)

    # BM25 scores
    for rank, result in enumerate(bm25_results, start=1):
        key = (result.get("source"), result.get("chunk_index"))
        # Normalize bm25 result to same key format
        if isinstance(result, dict) and "text" in result:
            key = (result.get("source"), result.get("chunk_index"))
        scores[key] += 1.0 / (K + rank)

    return scores

def hybrid_search(query: str, limit: int = 5) -> list[dict]:
    # retrieve from both sources
    vector_results = vector_search(query, limit=limit*2)
    bm25_raw = bm25.search(query, limit=limit*2)
    bm25_results = [_normalize_bm25_result(c) for c in bm25_raw]

    rrf_scores = _compute_rrf_scores(vector_results, bm25_results)

    all_results = {}
    for result in vector_results + bm25_results:
        key = (result.get("source"), result.get("chunk_index"))
        if key not in all_results:
            all_results[key] = result

    ranked = sorted(
        all_results.items(),
        key=lambda item: rrf_scores.get(item[0], 0),
        reverse=True
    )

    output = []
    for key, result in ranked[:limit]:
        result["rrf_score"] = round(rrf_scores[key], 4)
        output.append(result)

    return output