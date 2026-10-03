from functools import lru_cache

from app.core.config import settings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore


def qdrant_url() -> str:
    return f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"


# Built on first use, not at import: loading the model downloads/reads it
# from the HuggingFace cache, which made merely importing anything RAG-related
# slow and network-dependent (CLAUDE.md gotcha #1).
@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)


def create_vector_store(texts: list[str], metadatas: list[dict]):
    return QdrantVectorStore.from_texts(
        texts=texts,
        embedding=get_embeddings(),
        metadatas=metadatas,
        url=qdrant_url(),
        collection_name=settings.QDRANT_COLLECTION,
    )
