from celery import Celery
from app.core.config import settings

celery = Celery("forensic", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_track_started=True, result_expires=3600)

import app.workers.tasks  # noqa: E402 — registers run_pipeline with Celery
