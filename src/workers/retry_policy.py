"""Retry policy for Celery tasks with exponential backoff."""

import logging
from typing import Optional

from celery import Task
from requests.exceptions import HTTPError

logger = logging.getLogger(__name__)


class RetryableTask(Task):
    """Base task with retry logic and exponential backoff.

    Automatically retries on transient failures with exponential backoff.
    """

    autoretry_for = (HTTPError, ConnectionError, TimeoutError)
    retry_kwargs = {"max_retries": 5}
    retry_backoff = True  # Enable exponential backoff
    retry_backoff_max = 600  # Max 10 minutes between retries
    retry_jitter = True  # Add jitter to prevent thundering herd

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried.

        Args:
            exc: Exception that caused retry
            task_id: Unique ID of task
            args: Original task args
            kwargs: Original task kwargs
            einfo: Exception info
        """
        logger.warning(
            f"Task {self.name}[{task_id}] retrying: {exc}. "
            f"Retry {self.request.retries}/{self.max_retries}"
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails after all retries.

        Args:
            exc: Exception that caused failure
            task_id: Unique ID of task
            args: Original task args
            kwargs: Original task kwargs
            einfo: Exception info
        """
        logger.error(
            f"Task {self.name}[{task_id}] failed after {self.request.retries} retries: {exc}"
        )


def is_retryable_error(exc: Exception) -> bool:
    """Check if exception is retryable.

    Args:
        exc: Exception to check

    Returns:
        True if exception should trigger retry
    """
    # HTTP errors
    if isinstance(exc, HTTPError):
        if exc.response is not None:
            # Retry on 5xx errors and rate limits
            status_code = exc.response.status_code
            if status_code >= 500 or status_code == 429:
                return True
        return False

    # Network errors
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True

    # Don't retry by default
    return False


def calculate_retry_delay(
    retry_count: int,
    base_delay: int = 60,
    max_delay: int = 600,
) -> int:
    """Calculate retry delay with exponential backoff.

    Args:
        retry_count: Number of retries so far
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        Delay in seconds for next retry
    """
    # Exponential backoff: base_delay * 2^retry_count
    delay = base_delay * (2 ** retry_count)

    # Cap at max_delay
    return min(delay, max_delay)


def get_retry_countdown(
    exc: Exception,
    retry_count: int,
    max_retries: int = 5,
) -> Optional[int]:
    """Get retry countdown for exception.

    Args:
        exc: Exception that occurred
        retry_count: Current retry count
        max_retries: Maximum retries allowed

    Returns:
        Seconds to wait before retry, or None if should not retry
    """
    # Check if should retry
    if not is_retryable_error(exc):
        return None

    if retry_count >= max_retries:
        return None

    # Handle rate limit errors specially
    if isinstance(exc, HTTPError) and exc.response is not None:
        if exc.response.status_code == 429:
            # Check for Retry-After header
            retry_after = exc.response.headers.get("Retry-After")
            if retry_after:
                try:
                    return int(retry_after)
                except ValueError:
                    pass

            # Default rate limit backoff: 5 minutes
            return 300

    # Calculate exponential backoff
    return calculate_retry_delay(retry_count)


def retry_with_backoff(
    task: Task,
    exc: Exception,
    countdown: Optional[int] = None,
) -> None:
    """Retry task with exponential backoff.

    Args:
        task: Celery task instance
        exc: Exception that triggered retry
        countdown: Optional countdown override

    Raises:
        Retry: Celery retry exception
    """
    retry_count = task.request.retries
    max_retries = task.max_retries

    if countdown is None:
        countdown = get_retry_countdown(exc, retry_count, max_retries)

    if countdown is None:
        # Should not retry
        logger.error(f"Task {task.name} not retrying: {exc}")
        raise exc

    logger.warning(
        f"Task {task.name} retrying in {countdown}s "
        f"(attempt {retry_count + 1}/{max_retries}): {exc}"
    )

    raise task.retry(exc=exc, countdown=countdown)
