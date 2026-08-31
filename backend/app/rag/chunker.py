from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_documents(documents: list[dict]) -> list[dict]:

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=700,
        chunk_overlap=100
    )

    chunks = []

    for document in documents:
        split_texts = splitter.split_text(document["text"])

        for index, text in enumerate(split_texts):
            chunks.append(
                {
                    "text": text,
                    "source": document["source"],
                    "chunk_index": index
                }
            )

    return chunks