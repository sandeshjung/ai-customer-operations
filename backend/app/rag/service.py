# from app.rag.retriever import search_policy
from app.rag.hybrid_retriever import hybrid_search

def retrieve_policy(query: str, limit: int = 5) -> list[dict]:

    # return search_policy(query=query, limit=limit)
    return hybrid_search(query=query, limit=limit)