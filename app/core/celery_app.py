from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

# Create Celery instance
celery_app = Celery(
    "morning_brief",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.brief_tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
) 

# Optional Celery Beat schedule (daily brief)
delivery_time = getattr(settings, 'default_delivery_time', '08:00')
hour, minute = map(int, delivery_time.split(':'))
celery_app.conf.beat_schedule = {
    'daily-morning-brief': {
        'task': 'app.tasks.brief_tasks.generate_and_send_morning_brief',
        'schedule': crontab(hour=hour, minute=minute),
    },
    'weekly-token-refresh': {
        'task': 'app.tasks.brief_tasks.refresh_tokens',
        'schedule': crontab(hour=2, minute=0, day_of_week='sun'),
    },
}