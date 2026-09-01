from pathlib import Path

def build_metadata(chunk: dict) -> dict:
    source = chunk["source"]

    return {
        "source": source,
        "document_type": chunk["document_type"],
        "page": chunk["page"],
        "chunk_index": chunk["chunk_index"],
        "version": "1.0"
    }