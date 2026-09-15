#!/bin/sh
# Importing app.services.agent_service / triage_service (which
# event_consumer.py does at module level) transitively imports
# app.rag.retriever, which calls QdrantVectorStore.from_existing_collection
# at *import time* — that raises if the collection doesn't exist yet.
# On a fresh Qdrant volume (first `docker compose up`) nothing has ever
# run the ingestion script, so the worker would crash-loop forever.
# Ingest once up front if the collection is missing, then start the worker.
#
# This check talks to Qdrant directly instead of importing
# app.rag.vector_store — that module loads a real HuggingFace embedding
# model at import time (see CLAUDE.md), which would otherwise double the
# already-slow cold-start cost every single time the worker starts, just
# to answer a yes/no collection-existence question.
set -e

python -c "
from app.core.config import settings
from qdrant_client import QdrantClient
import sys
client = QdrantClient(url=f'http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}')
sys.exit(0 if client.collection_exists(settings.QDRANT_COLLECTION) else 1)
" || python backend/scripts/ingest_knowledge.py

exec python backend/scripts/run_worker.py
