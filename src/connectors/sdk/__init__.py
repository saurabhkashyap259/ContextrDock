"""Connector SDK for building workplace tool integrations."""

from src.connectors.sdk.base import ConnectorBase
from src.connectors.sdk.oauth import OAuth2Config, OAuth2Helper, OAuth2Token
from src.connectors.sdk.pagination import (
    CursorPaginator,
    PageResult,
    paginate_all,
    paginate_with_retry,
)
from src.connectors.sdk.rate_limiter import RateLimiter, RateLimitExceeded, rate_limit

__all__ = [
    "ConnectorBase",
    "OAuth2Helper",
    "OAuth2Config",
    "OAuth2Token",
    "rate_limit",
    "RateLimiter",
    "RateLimitExceeded",
    "CursorPaginator",
    "PageResult",
    "paginate_all",
    "paginate_with_retry",
]
