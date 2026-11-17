"""Celery Beat schedule; parser tasks will be added here."""

BEAT_SCHEDULE = {
    "worker-ping-every-minute": {
        "task": "workers.ping",
        "schedule": 60.0,
    },
}
