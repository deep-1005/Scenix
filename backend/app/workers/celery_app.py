from celery import Celery
from app.core.config import settings

celery = Celery("forensic", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_track_started=True,
    result_expires=3600,
    task_time_limit=1800,       # hard kill after 30 min — adjust to real FastGS runtime
    task_soft_time_limit=1700,  # raises SoftTimeLimitExceeded first, lets you catch+log
)

import app.workers.tasks  # noqa: E402 — registers run_pipeline with Celery