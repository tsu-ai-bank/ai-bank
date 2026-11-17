from src.workers.celery_app import celery_app


@celery_app.task(name="workers.ping")
def ping() -> str:
    """Check that a queued task can be executed by a worker."""
    return "pong"
