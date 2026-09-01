from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=700,
    chunk_overlap=100
)

def chunk_documents(documents: list[dict]) -> list[dict]:
    chunks = []

    for document in documents:
        for page in document["pages"]:
            page_text = page["text"]
            split_texts = splitter.split_text(page_text)

            for chunk_index, text in enumerate(split_texts):
                chunks.append(
                    {
                        "text": text,
                        "source": document["source"],
                        "document_type": document["document_type"],
                        "page": page["page"],
                        "chunk_index": chunk_index,
                    }
                )

    return chunks