from functools import lru_cache

from app.core.tracing import traced
from app.rag.hybrid_retriever import hybrid_search


# Simple in-memory cache for policy retrieval results
@lru_cache(maxsize=50)
def retrieve_policy_cached(query: str, limit: int = 5) -> list[dict]:
    return hybrid_search(query=query, limit=limit)


def retrieve_policy(query: str, limit: int = 5) -> list[dict]:
    # Normalize query for caching
    cache_key = query.lower().strip()[:50]

    hits_before = retrieve_policy_cached.cache_info().hits
    with traced("rag.retrieve_policy", tracer_name="rag", query=query[:200], limit=limit) as span:
        results = retrieve_policy_cached(cache_key, limit=limit)
        cache_hit = retrieve_policy_cached.cache_info().hits > hits_before
        span.set_attribute("cache_hit", cache_hit)
        span.set_attribute("result_count", len(results))
        sources = {r.get("source", "unknown") for r in results if isinstance(r, dict)}
        if sources:
            span.set_attribute("sources", ",".join(sorted(sources)))
        return results
