#!/bin/bash

# Start Celery workers for parallel embedding processing
# These workers only process embedding and storage queues
# Using prefork pool for parallel processing since they don't use marker-pdf

echo "Starting Celery embedding workers..."
echo "Queues: embedding, storage"
echo "Pool: prefork (multi-process for parallel execution)"
echo "Concurrency: 4 workers"
echo ""

celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --queues=embedding,storage \
  --pool=prefork \
  --hostname=embedding_worker@%h
