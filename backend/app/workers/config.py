MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
DEAD_LETTER_STREAM = "customer_operations_dead_letter"

# Defined here (not in event_consumer.py) so the API can inspect queue
# position without importing the worker module, which pulls in the agents
# and RAG stack at import time (CLAUDE.md gotcha #1).
CONSUMER_GROUP = "customer_operations_workers"
