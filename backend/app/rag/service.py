from functools import lru_cache

from app.core.tracing import traced
from app.rag.hybrid_retriever import hybrid_search


# Simple in-memory cache for policy retrieval results
@lru_cache(maxsize=50)
def retrieve_policy_cached(query: str, limit: int = 5) -> tuple[dict, ...]:
    # A tuple, so the cached entry itself can't be appended to or reordered.
    return tuple(hybrid_search(query=query, limit=limit))


def normalize_query(query: str) -> str:
    """Cache key and search text: lowercased, whitespace collapsed. Lowercasing
    doesn't change results (BM25 tokenises case-insensitively and the
    embedding model is uncased). The whole query is kept: an earlier version
    truncated it to 50 characters, so long queries sharing a prefix collided
    in the cache and were searched on that prefix alone."""
    return " ".join(query.lower().split())


def retrieve_policy(query: str, limit: int = 5) -> list[dict]:
    cache_key = normalize_query(query)

    hits_before = retrieve_policy_cached.cache_info().hits
    with traced(
        "rag.retrieve_policy", tracer_name="rag", query=query[:200], limit=limit
    ) as span:
        cached = retrieve_policy_cached(cache_key, limit=limit)
        cache_hit = retrieve_policy_cached.cache_info().hits > hits_before
        span.set_attribute("cache_hit", cache_hit)
        span.set_attribute("result_count", len(cached))
        sources = {r.get("source", "unknown") for r in cached if isinstance(r, dict)}
        if sources:
            span.set_attribute("sources", ",".join(sorted(sources)))
        # Copies, so a caller mutating a result can't change what later
        # cache hits return.
        return [dict(r) if isinstance(r, dict) else r for r in cached]
