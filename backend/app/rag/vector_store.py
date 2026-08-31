from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from app.core.config import settings

embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)

qdrant_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
client = QdrantClient(url=qdrant_url)

def create_vector_store(
        texts: list[str],
        metadatas: list[dict]
):
    return QdrantVectorStore.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        url=qdrant_url,
        collection_name=settings.QDRANT_COLLECTION
    )