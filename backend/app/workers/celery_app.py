from celery import Celery

from app.core.config import get_settings

settings = get_settings()
_broker_url = settings.celery_broker_url or settings.redis_url or "redis://127.0.0.1:16379/0"
_result_backend = settings.celery_result_backend or _broker_url

celery_app = Celery(
    "docmind",
    broker=_broker_url,
    backend=_result_backend,
)
celery_app.conf.update(
    accept_content=["json"],
    enable_utc=True,
    result_serializer="json",
    task_serializer="json",
    task_track_started=True,
    timezone="UTC",
)
