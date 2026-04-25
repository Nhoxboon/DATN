#!/bin/bash

# Start all Celery workers for pdp8-rag project
# - Document processing worker (solo pool for marker-pdf compatibility)
# - Embedding workers (prefork pool for parallel processing)

echo "============================================================"
echo "Starting Celery Workers"
echo "============================================================"
echo ""

# Start document processing worker in background
echo "Starting document processing worker (solo pool)..."
celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=1 \
  --queues=document_processing \
  --pool=solo \
  --hostname=document_worker@%h &

DOCUMENT_WORKER_PID=$!
echo "  ✓ Document worker started (PID: $DOCUMENT_WORKER_PID)"
echo ""

# Start embedding workers in background
echo "Starting embedding workers (prefork pool, 4 concurrent)..."
celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --queues=embedding,storage \
  --pool=prefork \
  --hostname=embedding_worker@%h &

EMBEDDING_WORKER_PID=$!
echo "  ✓ Embedding workers started (PID: $EMBEDDING_WORKER_PID)"
echo ""

echo "============================================================"
echo "All workers started!"
echo "============================================================"
echo "Document worker PID: $DOCUMENT_WORKER_PID"
echo "Embedding worker PID: $EMBEDDING_WORKER_PID"
echo ""
echo "Press Ctrl+C to stop all workers"
echo ""

# Trap SIGINT and SIGTERM to clean up both workers
trap "echo ''; echo 'Stopping all workers...'; kill $DOCUMENT_WORKER_PID $EMBEDDING_WORKER_PID; exit" SIGINT SIGTERM

# Wait for both processes
wait
