"""Celery application and Beat scheduler configuration."""

import logging

from celery import Celery
from celery.schedules import crontab

from src.config.settings import settings
from src.database import get_db
from src.models.connector import Connector

logger = logging.getLogger(__name__)

# Initialize Celery app
celery_app = Celery(
    "contextdock",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,  # One task at a time
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["src.workers"])


def parse_cron_expression(cron_expr: str) -> crontab:
    """Parse cron expression into celery crontab object.

    Args:
        cron_expr: Cron expression like "0 */3 * * *"

    Returns:
        Celery crontab schedule object

    Raises:
        ValueError: If cron expression is invalid
    """
    try:
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression: {cron_expr}. Expected 5 parts."
            )

        minute, hour, day_of_month, month_of_year, day_of_week = parts

        return crontab(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
        )
    except Exception as e:
        logger.error(f"Failed to parse cron expression '{cron_expr}': {e}")
        raise ValueError(f"Invalid cron expression: {cron_expr}") from e


def get_beat_schedule() -> dict:
    """Generate Celery Beat schedule from active connectors.

    Returns:
        Dict of scheduled tasks for Celery Beat
    """
    schedule = {}

    try:
        db = next(get_db())

        # Fetch all active connectors
        connectors = db.query(Connector).filter_by(is_active=True).all()

        for connector in connectors:
            # Get sync schedule (use default if not specified)
            sync_schedule = connector.sync_schedule or "0 */6 * * *"  # Default: 6 hours

            try:
                # Parse cron expression
                cron_schedule = parse_cron_expression(sync_schedule)

                # Add to schedule
                task_name = f"sync-connector-{connector.id}"
                schedule[task_name] = {
                    "task": "src.workers.sync_task.run_connector_sync",
                    "schedule": cron_schedule,
                    "args": (connector.id,),
                    "options": {
                        "expires": 3600,  # Task expires after 1 hour if not picked up
                    },
                }

                logger.debug(
                    f"Added connector {connector.id} ({connector.connector_type}) "
                    f"to beat schedule with cron: {sync_schedule}"
                )

            except ValueError as e:
                logger.warning(
                    f"Skipping connector {connector.id} due to invalid cron: {e}"
                )
                continue

        db.close()

    except Exception as e:
        logger.error(f"Failed to generate beat schedule: {e}")

    return schedule


# Configure Celery Beat schedule
celery_app.conf.beat_schedule = get_beat_schedule()


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks on Celery Beat startup.

    This is called after Celery configuration is complete.
    """
    logger.info("Celery Beat scheduler initialized")
    schedule = get_beat_schedule()
    logger.info(f"Loaded {len(schedule)} connector sync schedules")
    for task_name, task_config in schedule.items():
        logger.info(
            f"  - {task_name}: {task_config['schedule']} -> {task_config['task']}"
        )
