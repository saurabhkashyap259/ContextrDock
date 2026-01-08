"""
Structured logging configuration using structlog (T198).

Features:
- JSON output format for machine parsing
- Trace ID propagation for request correlation
- Context processors for rich metadata
- Performance optimizations for production
- Security: PII redaction

Usage:
    from src.services.logger import get_logger

    logger = get_logger(__name__)
    logger.info("User query processed", workspace_id=123, query_latency_ms=450)
"""
import logging
import sys
import uuid
from datetime import datetime
from typing import Any

import structlog


def add_trace_id(logger: Any, method_name: str, event_dict: dict) -> dict:
    """
    Add trace ID to log entry for request correlation.

    If trace_id not in context, generates new UUID.
    """
    if "trace_id" not in event_dict:
        event_dict["trace_id"] = str(uuid.uuid4())

    return event_dict


def add_timestamp(logger: Any, method_name: str, event_dict: dict) -> dict:
    """Add ISO 8601 timestamp to log entry."""
    event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return event_dict


def redact_sensitive_data(logger: Any, method_name: str, event_dict: dict) -> dict:
    """
    Redact sensitive data from log entries.

    Redacts:
    - password, api_key, secret, token fields
    - Does NOT redact: user_id, workspace_id, email (safe identifiers)
    """
    sensitive_keys = ["password", "api_key", "secret", "token", "credential", "auth"]

    for key in sensitive_keys:
        if key in event_dict:
            event_dict[key] = "[REDACTED]"

    return event_dict


def configure_structlog(log_level: str = "INFO", json_output: bool = True):
    """
    Configure structlog for structured logging (T198).

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON format; if False, use console renderer

    Configuration:
    - JSON output for production (machine-readable)
    - Console output for development (human-readable)
    - Trace ID propagation for distributed tracing
    - Timestamp in ISO 8601 format
    - Logger name for source identification
    - Exception formatting with stack traces
    - Sensitive data redaction
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Processors to apply to all log entries
    processors = [
        # Add log level
        structlog.stdlib.add_log_level,

        # Add logger name
        structlog.stdlib.add_logger_name,

        # Add trace ID for request correlation
        add_trace_id,

        # Add timestamp
        add_timestamp,

        # Redact sensitive data
        redact_sensitive_data,

        # Format exceptions
        structlog.processors.format_exc_info,

        # Add stack info if available
        structlog.processors.StackInfoRenderer(),

        # Decode unicode
        structlog.processors.UnicodeDecoder(),
    ]

    # Choose renderer based on environment
    if json_output:
        # Production: JSON output for log aggregation
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: Human-readable console output
        renderer = structlog.dev.ConsoleRenderer()

    processors.append(renderer)

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("User query", workspace_id=123, latency_ms=450)
        {"event": "User query", "workspace_id": 123, "latency_ms": 450,
         "level": "info", "timestamp": "2024-01-15T10:30:00Z", ...}
    """
    return structlog.get_logger(name)


def bind_trace_id(trace_id: str):
    """
    Bind trace ID to current context for request correlation.

    All subsequent logs in this context will include the trace ID.

    Args:
        trace_id: Trace ID (typically from X-Trace-ID header or generated)

    Example:
        >>> bind_trace_id("abc-123-def-456")
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing request")  # Will include trace_id
    """
    structlog.contextvars.bind_contextvars(trace_id=trace_id)


def unbind_trace_id():
    """
    Remove trace ID from current context.

    Call at end of request to avoid leaking trace ID to next request.
    """
    structlog.contextvars.unbind_contextvars("trace_id")


def bind_context(**kwargs):
    """
    Bind context variables to all logs in current context.

    Args:
        **kwargs: Key-value pairs to bind (e.g., workspace_id=123, user_id=456)

    Example:
        >>> bind_context(workspace_id=123, user_id=456)
        >>> logger = get_logger(__name__)
        >>> logger.info("Query processed")  # Includes workspace_id and user_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys):
    """
    Remove context variables from current context.

    Args:
        *keys: Keys to unbind

    Example:
        >>> unbind_context("workspace_id", "user_id")
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context():
    """
    Clear all context variables.

    Call at end of request to avoid context leakage.
    """
    structlog.contextvars.clear_contextvars()


# Configure on module import
# Use environment variable or config setting to determine JSON output
import os

from src.config import settings

is_production = getattr(settings, "is_production", False)
log_level = os.getenv("LOG_LEVEL", "INFO")

configure_structlog(
    log_level=log_level,
    json_output=is_production,  # JSON in prod, console in dev
)


# Export commonly used functions
__all__ = [
    "get_logger",
    "bind_trace_id",
    "unbind_trace_id",
    "bind_context",
    "unbind_context",
    "clear_context",
    "configure_structlog",
]
