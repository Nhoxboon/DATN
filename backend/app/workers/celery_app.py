"""Celery application configuration."""

import logging
import multiprocessing
multiprocessing.set_start_method('spawn', force=True)

from celery import Celery
from celery.signals import worker_ready
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Use single Redis DB with key prefixes
redis_url = settings.redis_url

# Initialize Celery app
celery_app = Celery(
    "datn_backend",
    broker=redis_url,
    backend=redis_url,
    include=[
        "app.workers.tasks.document",
        "app.workers.tasks.embedding",
        "app.workers.tasks.storage",
        "app.modules.audio_overviews.tasks",
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3000,  # 50 minutes soft limit
    worker_prefetch_multiplier=1,  # Disable prefetching for fair distribution
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    result_expires=86400,  # Results expire after 24 hours
    task_routes={
        "app.workers.tasks.document.*": {"queue": "document_processing"},
        "app.workers.tasks.embedding.*": {"queue": "embedding"},
        "app.workers.tasks.storage.*": {"queue": "storage"},
        "app.modules.audio_overviews.tasks.*": {"queue": "audio_overviews"},
    },
    task_annotations={
        "app.workers.tasks.embedding.generate_embedding_task": {
            "rate_limit": "100/m",  # 100 embeddings per minute
        }
    },
)

# Configure result backend settings
celery_app.conf.result_backend_transport_options = {
    "retry_policy": {
        "timeout": 5.0
    }
}


@worker_ready.connect
def log_worker_ready(sender=None, **_kwargs):
    logger.info(
        "DATN worker ready: document_processing_mode=%s redis_url=%s uploads_dir=%s queues=%s",
        settings.document_processing_mode,
        settings.redis_url,
        settings.uploads_dir,
        "document_processing,embedding,storage,audio_overviews",
    )
