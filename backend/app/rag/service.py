from app.rag.retriever import search_policy

def retrieve_policy(query: str, limit: int = 5) -> list[dict]:

    return search_policy(query=query, limit=limit)