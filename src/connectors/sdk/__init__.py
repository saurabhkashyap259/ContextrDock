"""Connector SDK for building workplace tool integrations."""

from src.connectors.sdk.base import ConnectorBase
from src.connectors.sdk.oauth import OAuth2Helper, OAuth2Config, OAuth2Token
from src.connectors.sdk.rate_limiter import rate_limit, RateLimiter, RateLimitExceeded
from src.connectors.sdk.pagination import CursorPaginator, PageResult, paginate_all, paginate_with_retry

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
