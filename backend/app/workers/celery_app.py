"""
Celery application configuration
"""
from celery import Celery
from kombu import Queue

from app.core.config import settings

celery_app = Celery(
    "presenter",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.RENDER_TASK_TIMEOUT_SEC,
    task_soft_time_limit=settings.RENDER_TASK_TIMEOUT_SEC - 60,
    worker_prefetch_multiplier=1,  # For long-running tasks
    task_acks_late=True,
)

# Define queues with concurrency settings
# NOTE: For production, run convert queue worker with: 
#   celery -A app.workers.celery_app worker -Q convert_queue --concurrency=1
# This ensures LibreOffice doesn't run multiple conversions in parallel
celery_app.conf.task_queues = (
    Queue("celery"),
    Queue("convert_queue"),  # LibreOffice - run with concurrency=1
    Queue("tts"),
    Queue("render"),
    Queue("translate"),
)

# Default queue
celery_app.conf.task_default_queue = "celery"

# Task routing
celery_app.conf.task_routes = {
    "app.workers.tasks.convert_pptx_task": {"queue": "convert_queue"},
    "app.workers.tasks.tts_*": {"queue": "tts"},
    "app.workers.tasks.render_*": {"queue": "render"},
    "app.workers.tasks.translate_*": {"queue": "translate"},
}

# Retry policies
celery_app.conf.task_annotations = {
    "app.workers.tasks.tts_slide_task": {
        "max_retries": 3,
        "default_retry_delay": 10,
    },
    "app.workers.tasks.convert_pptx_task": {
        "max_retries": 1,
        "default_retry_delay": 5,
        # Rate limit: at most 1 task per 5 seconds to avoid LibreOffice conflicts
        "rate_limit": "12/m",
    },
    "app.workers.tasks.render_language_task": {
        "max_retries": 1,
        "default_retry_delay": 10,
    },
}

