"""
Action expiration cleanup task (T162).

Celery task that runs hourly to:
1. Mark expired PENDING_APPROVAL actions as EXPIRED
2. Clean up old EXPIRED/CANCELLED actions past retention period
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from contextlib import contextmanager

from celery import Task
from sqlalchemy.orm import Session

from src.models.agent_action import AgentAction, ActionStatus
from src.database import SessionLocal

logger = logging.getLogger(__name__)


@contextmanager
def get_db_session():
    """Get database session context manager."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def expire_old_actions(db: Session) -> int:
    """
    Mark expired pending actions as EXPIRED.
    
    Finds all actions with:
    - status = PENDING_APPROVAL
    - expires_at <= current time
    
    Updates their status to EXPIRED.
    
    Args:
        db: Database session
    
    Returns:
        Number of actions marked as expired
    """
    now = datetime.utcnow()
    
    # Find expired pending actions
    expired_actions = (
        db.query(AgentAction)
        .filter(
            AgentAction.status == ActionStatus.PENDING_APPROVAL,
            AgentAction.expires_at <= now
        )
        .all()
    )
    
    # Mark each as expired
    expired_count = 0
    for action in expired_actions:
        action.mark_as_expired()
        expired_count += 1
        logger.info(f"Marked action {action.id} as expired")
    
    # Commit changes
    db.commit()
    
    logger.info(f"Expired {expired_count} actions")
    return expired_count


def cleanup_expired_actions(db: Session, retention_days: int = 7) -> int:
    """
    Delete old expired/cancelled actions past retention period.
    
    Removes actions with:
    - status in (EXPIRED, CANCELLED)
    - created_at older than retention_days
    
    Executed and failed actions are kept for audit purposes.
    
    Args:
        db: Database session
        retention_days: Number of days to retain expired actions
    
    Returns:
        Number of actions deleted
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    
    # Delete old expired/cancelled actions
    deleted_count = (
        db.query(AgentAction)
        .filter(
            AgentAction.status.in_([ActionStatus.EXPIRED, ActionStatus.CANCELLED]),
            AgentAction.created_at < cutoff_date
        )
        .delete(synchronize_session=False)
    )
    
    db.commit()
    
    logger.info(f"Cleaned up {deleted_count} old actions (retention: {retention_days} days)")
    return deleted_count


def action_cleanup_task() -> Dict[str, Any]:
    """
    Celery task for action cleanup.
    
    Runs hourly to:
    1. Expire old pending actions
    2. Clean up expired actions past retention
    
    Returns:
        Dictionary with task results and metrics
    """
    start_time = datetime.utcnow()
    
    try:
        with get_db_session() as db:
            # Expire old actions
            expired_count = expire_old_actions(db)
            
            # Clean up old expired actions (7 day retention)
            cleanup_count = cleanup_expired_actions(db, retention_days=7)
            
            # Calculate execution time
            execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            result = {
                "success": True,
                "expired": expired_count,
                "cleaned_up": cleanup_count,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(
                f"Action cleanup completed: expired={expired_count}, "
                f"cleaned_up={cleanup_count}, time={execution_time_ms}ms"
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Action cleanup task failed: {e}", exc_info=True)
        raise


def get_task_schedule() -> Dict[str, Any]:
    """
    Get Celery task schedule configuration.
    
    Returns:
        Schedule configuration for Celery beat
    """
    return {
        "schedule_type": "crontab",
        "hour": "*",  # Every hour
        "minute": "0",  # At the top of the hour
        "retry": {
            "max_retries": 3,
            "retry_backoff": True,
            "retry_backoff_max": 600  # 10 minutes max
        }
    }


# Celery task decorator would be applied in actual Celery app configuration
# @celery_app.task(bind=True, name="action_cleanup_task")
class ActionCleanupTask(Task):
    """
    Celery task class for action cleanup.
    
    Configured to run hourly and retry on failures.
    """
    name = "action_cleanup_task"
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    
    def run(self):
        """Execute action cleanup task."""
        return action_cleanup_task()
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(
            f"Action cleanup task {task_id} failed: {exc}",
            exc_info=einfo
        )
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        logger.info(
            f"Action cleanup task {task_id} succeeded: "
            f"expired={retval['expired']}, cleaned_up={retval['cleaned_up']}"
        )
