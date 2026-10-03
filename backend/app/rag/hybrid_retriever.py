from collections import defaultdict
from functools import lru_cache

from app.rag.bm25 import BM25Retriever
from app.rag.chunker import chunk_documents
from app.rag.loader import load_documents
from app.rag.retriever import search_policy as vector_search

K = 60


# Built on first search, not at import (reads and chunks every policy PDF).
@lru_cache(maxsize=1)
def _bm25_index() -> BM25Retriever:
    return BM25Retriever(chunk_documents(load_documents()))


def chunk_key(result: dict) -> tuple:
    """Identity of a chunk across both retrievers. chunk_index restarts at 0
    on every page, so the page is part of the key — without it, chunk 0 of
    page 1 and chunk 0 of page 2 of the same PDF collide: one is dropped and
    its RRF score is credited to the other."""
    return (result.get("source"), result.get("page"), result.get("chunk_index"))


def _normalize_bm25_result(chunk: dict) -> dict:
    return {
        "content": chunk["text"],
        "source": chunk["source"],
        "page": chunk.get("page"),
        "chunk_index": chunk.get("chunk_index"),
        "version": "1.0",
        "score": None,
    }


def _compute_rrf_scores(vector_results: list[dict], bm25_results: list[dict]) -> dict:
    """score = Σ 1 / (K + rank) over both retrievers' rankings (rank from 1)."""
    scores = defaultdict(float)

    for results in (vector_results, bm25_results):
        for rank, result in enumerate(results, start=1):
            scores[chunk_key(result)] += 1.0 / (K + rank)

    return scores


def hybrid_search(query: str, limit: int = 5) -> list[dict]:
    # retrieve from both sources
    vector_results = vector_search(query, limit=limit * 2)
    bm25_raw = _bm25_index().search(query, limit=limit * 2)
    bm25_results = [_normalize_bm25_result(c) for c in bm25_raw]

    rrf_scores = _compute_rrf_scores(vector_results, bm25_results)

    all_results = {}
    for result in vector_results + bm25_results:
        all_results.setdefault(chunk_key(result), result)

    ranked = sorted(
        all_results.items(), key=lambda item: rrf_scores.get(item[0], 0), reverse=True
    )

    output = []
    for key, result in ranked[:limit]:
        result["rrf_score"] = round(rrf_scores[key], 4)
        output.append(result)

    return output
