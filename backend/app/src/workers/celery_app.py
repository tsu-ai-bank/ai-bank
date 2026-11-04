from celery import Celery

from src.core.config import get_settings
from src.workers.schedule import BEAT_SCHEDULE

redis_url = get_settings().redis_url
if not redis_url:
    raise RuntimeError("Set REDIS_URL before starting the Celery worker or beat.")

celery_app = Celery(
    "ai_bank",
    broker=redis_url,
    backend=redis_url,
    include=["src.workers.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    beat_schedule=BEAT_SCHEDULE,
)
