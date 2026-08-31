"""
app/worker.py
-------------
Celery application definition.

Celery is a distributed task queue.  It picks up jobs from Redis and
executes them in background worker processes, completely separate from
the FastAPI web server.

Usage:
    celery -A app.worker worker --loglevel=info
"""

import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Both the broker (where tasks are submitted) and the result backend
# (where task results are stored) point to Redis.
celery_app = Celery(
    "pr_review_bot",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Retry a failed task up to 3 times with exponential back-off
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
