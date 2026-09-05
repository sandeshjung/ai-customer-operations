# from app.rag.retriever import search_policy
from app.rag.hybrid_retriever import hybrid_search
from functools import lru_cache

# Simple in-memory cache for policy retrieval results
@lru_cache(maxsize=50)
def retrieve_policy_cached(query: str, limit: int = 5) -> list[dict]:
    return hybrid_search(query=query, limit=limit)

def retrieve_policy(query: str, limit: int = 5) -> list[dict]:
    # return search_policy(query=query, limit=limit)

    # Normalize query for caching
    cache_key = query.lower().strip()[:50]
    # return hybrid_search(query=query, limit=limit)
    return retrieve_policy_cached(cache_key, limit=limit)