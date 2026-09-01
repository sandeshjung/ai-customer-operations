from rank_bm25 import BM25Okapi

class BM25Retriever:

    def __init__(self, documents: list[dict]):
        self.documents = documents

        tokenized_documents = [
            document["text"].lower().split()
            for document in documents
        ]

        self.bm25 = BM25Okapi(tokenized_documents)

    def search(self, query: str, limit: int = 5) -> list[dict]:

        tokens = query.lower().split()

        results = self.bm25.get_top_n(tokens, self.documents, n=limit)

        return results