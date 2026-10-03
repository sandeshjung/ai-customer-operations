#!/bin/sh
# On a fresh Qdrant volume (first `docker compose up`) nothing has ever run
# the ingestion script, so every policy search would fail. Ingest once up
# front if the collection is missing, then start the worker.
#
# This check talks to Qdrant directly rather than through app.rag: it only
# needs a yes/no answer, so there's no reason to load the embedding model
# (see CLAUDE.md gotchas #1 and #9).
set -e

python -c "
from app.core.config import settings
from qdrant_client import QdrantClient
import sys
client = QdrantClient(url=f'http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}')
sys.exit(0 if client.collection_exists(settings.QDRANT_COLLECTION) else 1)
" || python backend/scripts/ingest_knowledge.py

exec python backend/scripts/run_worker.py
