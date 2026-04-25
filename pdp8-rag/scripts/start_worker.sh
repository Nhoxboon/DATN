#!/bin/bash

# Start Celery worker for pdp8-rag project

echo "Starting Celery document processing worker..."
echo "Queue: document_processing only"
echo "Pool: solo (single-threaded for marker-pdf PyTorch model compatibility)"
echo "Note: Use start_embedding_workers.sh for parallel embedding processing"
echo ""

celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=1 \
  --queues=document_processing \
  --pool=solo \
  --hostname=document_worker@%h
