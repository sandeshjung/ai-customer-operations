#!/bin/sh
# Importing app.services.agent_service / triage_service (which
# event_consumer.py does at module level) transitively imports
# app.rag.retriever, which calls QdrantVectorStore.from_existing_collection
# at *import time* — that raises if the collection doesn't exist yet.
# On a fresh Qdrant volume (first `docker compose up`) nothing has ever
# run the ingestion script, so the worker would crash-loop forever.
# Ingest once up front if the collection is missing, then start the worker.
set -e

python -c "
from app.core.config import settings
from app.rag.vector_store import client
import sys
sys.exit(0 if client.collection_exists(settings.QDRANT_COLLECTION) else 1)
" || python backend/scripts/ingest_knowledge.py

exec python backend/scripts/run_worker.py
