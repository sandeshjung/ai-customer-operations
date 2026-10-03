import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.rag import hybrid_retriever, retriever


def _vector(source, page, chunk_index, text):
    return {"content": text, "source": source, "page": page, "chunk_index": chunk_index}


class _FakeBM25:
    def __init__(self, chunks):
        self.chunks = chunks

    def search(self, query, limit=5):
        return self.chunks[:limit]


def _bm25_chunk(source, page, chunk_index, text):
    return {"text": text, "source": source, "page": page, "chunk_index": chunk_index}


def test_same_chunk_index_on_different_pages_are_distinct_results():
    """Regression: chunk_index restarts on every page, so keying chunks by
    (source, chunk_index) merged chunk 0 of page 1 with chunk 0 of page 2 —
    one passage vanished and its score was credited to the other."""
    vector = [
        _vector("shipping_policy.pdf", 1, 0, "page one text"),
        _vector("shipping_policy.pdf", 2, 0, "page two text"),
    ]
    with (
        patch.object(hybrid_retriever, "vector_search", return_value=vector),
        patch.object(hybrid_retriever, "_bm25_index", return_value=_FakeBM25([])),
    ):
        results = hybrid_retriever.hybrid_search("delay", limit=5)

    assert {(r["page"], r["content"]) for r in results} == {
        (1, "page one text"),
        (2, "page two text"),
    }


def test_chunk_found_by_both_retrievers_is_fused_and_ranked_first():
    vector = [
        _vector("refund_policy.pdf", 3, 1, "vector-only"),
        _vector("refund_policy.pdf", 2, 0, "both"),
    ]
    bm25 = [
        _bm25_chunk("refund_policy.pdf", 2, 0, "both"),
        _bm25_chunk("refund_policy.pdf", 1, 0, "bm25-only"),
    ]
    with (
        patch.object(hybrid_retriever, "vector_search", return_value=vector),
        patch.object(hybrid_retriever, "_bm25_index", return_value=_FakeBM25(bm25)),
    ):
        results = hybrid_retriever.hybrid_search("refund", limit=5)

    assert results[0]["content"] == "both"
    assert len(results) == 3
    # 1/(60+2) from vector + 1/(60+1) from BM25
    assert results[0]["rrf_score"] == round(1 / 62 + 1 / 61, 4)


class _FakeVectorStore:
    def __init__(self, scored):
        self.scored = scored

    def similarity_search_with_score(self, query, k):
        return self.scored[:k]


class _Doc:
    def __init__(self, text, page):
        self.page_content = text
        self.metadata = {"source": "s.pdf", "page": page, "chunk_index": 0}


def test_vector_search_uses_configurable_similarity_cutoff(monkeypatch):
    store = _FakeVectorStore(
        [(_Doc("strong", 1), 0.7), (_Doc("ok", 2), 0.5), (_Doc("weak", 3), 0.3)]
    )
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.45)

    with patch.object(retriever, "get_vector_store", return_value=store):
        default = [r["content"] for r in retriever.search_policy("q")]
        strict = [r["content"] for r in retriever.search_policy("q", min_score=0.6)]

    assert default == ["strong", "ok"]
    assert strict == ["strong"]


def test_importing_rag_needs_no_model_or_qdrant():
    """Regression for CLAUDE.md gotcha #1: importing the RAG chain used to
    load the HuggingFace model and connect to Qdrant at import time. Import it
    in a fresh interpreter with the HF hub offline and Qdrant unreachable."""
    backend = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": str(backend),
        "HF_HUB_OFFLINE": "1",
        "QDRANT_HOST": "qdrant.invalid",
        "QDRANT_PORT": "1",
        "OTEL_ENABLED": "false",
    }
    code = (
        "import app.rag.service, app.rag.hybrid_retriever, app.rag.retriever;"
        "from app.rag.vector_store import get_embeddings;"
        "from app.rag.retriever import get_vector_store;"
        "assert get_embeddings.cache_info().currsize == 0;"
        "assert get_vector_store.cache_info().currsize == 0"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
