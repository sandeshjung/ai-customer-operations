from app.rag.loader import load_documents
from app.rag.chunker import chunk_documents
from app.rag.vector_store import create_vector_store
from app.rag.metadata import build_metadata

def main():

    print("Loading documents...")

    documents = load_documents()

    print(f"Loaded {len(documents)} documents")

    chunks = chunk_documents(documents)

    print(f"Created {len(chunks)} chunks")

    texts = [chunk["text"] for chunk in chunks]

    metadatas = [
        build_metadata(chunk)
        for chunk in chunks
    ]

    print("Creating Qdrant collection...")

    create_vector_store(texts=texts, metadatas=metadatas)
    print("Knowledge ingestion complete.")

if __name__ == "__main__":
    main()