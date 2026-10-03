from functools import lru_cache

from app.core.config import settings
from app.rag.vector_store import get_embeddings, qdrant_url
from langchain_qdrant import QdrantVectorStore


# Connected on first search, not at import. If the collection doesn't exist
# yet this raises then, and — since lru_cache doesn't cache exceptions — the
# next search tries again (e.g. after the worker's start-up ingestion).
@lru_cache(maxsize=1)
def get_vector_store() -> QdrantVectorStore:
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embeddings(),
        url=qdrant_url(),
        collection_name=settings.QDRANT_COLLECTION,
    )


def search_policy(
    query: str,
    limit: int = 5,
    min_score: float | None = None,
) -> list[dict]:
    """Vector search over the policy chunks. Results below min_score
    (cosine similarity; default settings.RAG_MIN_SIMILARITY) are dropped."""
    threshold = settings.RAG_MIN_SIMILARITY if min_score is None else min_score

    results = get_vector_store().similarity_search_with_score(query, k=limit)

    output = []

    for document, score in results:
        if score < threshold:
            continue

        output.append(
            {
                "content": document.page_content,
                "source": document.metadata.get("source"),
                "page": document.metadata.get("page"),
                "chunk_index": document.metadata.get("chunk_index"),
                "version": document.metadata.get("version"),
                "score": float(score),
            }
        )

    return output
