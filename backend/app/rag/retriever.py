from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore

from app.core.config import settings

embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)

qdrant_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
vector_store = QdrantVectorStore.from_existing_collection(
    embedding=embeddings,
    url=qdrant_url,
    collection_name=settings.QDRANT_COLLECTION
)

def search_policy(
        query: str,
        limit: int=5,
) -> list[dict]:

    results = vector_store.similarity_search_with_score(query, k=limit)

    output = []

    for document, score in results:
        if score < 0.6:
            continue

        output.append(
            {
                "content": document.page_content,
                "source": document.metadata.get("source"),
                "page": document.metadata.get("page"),
                "chunk_index": document.metadata.get("chunk_index"),
                "version": document.metadata.get("version"),
                "score": float(score)
            }
        )

    return output
