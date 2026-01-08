"""
Prometheus metrics middleware for FastAPI (T199).

Tracks:
- Query latency (histogram)
- Sync success rate (counter)
- Active requests (gauge)
- Response status codes (counter)
- Vector search latency (histogram)
- Embedding generation time (histogram)
"""
import time
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import Response as FastAPIResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# Define metrics
REQUEST_COUNT = Counter(
    "contextdock_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "contextdock_request_latency_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

ACTIVE_REQUESTS = Gauge(
    "contextdock_active_requests",
    "Number of requests currently being processed",
)

QUERY_LATENCY = Histogram(
    "contextdock_query_latency_seconds",
    "Query processing latency in seconds",
    ["workspace_id"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

VECTOR_SEARCH_LATENCY = Histogram(
    "contextdock_vector_search_latency_seconds",
    "Vector search latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0],
)

EMBEDDING_LATENCY = Histogram(
    "contextdock_embedding_latency_seconds",
    "Embedding generation latency in seconds",
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0],
)

SYNC_SUCCESS = Counter(
    "contextdock_sync_success_total",
    "Total number of successful syncs",
    ["connector_type"],
)

SYNC_FAILURE = Counter(
    "contextdock_sync_failure_total",
    "Total number of failed syncs",
    ["connector_type", "error_type"],
)

DOCUMENTS_INGESTED = Counter(
    "contextdock_documents_ingested_total",
    "Total number of documents ingested",
    ["source_type"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "contextdock_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["service"],
)


async def prometheus_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware to track request metrics.

    Records:
    - Request count by method, endpoint, status
    - Request latency by method, endpoint
    - Active requests count
    """
    # Skip metrics endpoint itself
    if request.url.path == "/metrics":
        return await call_next(request)

    # Increment active requests
    ACTIVE_REQUESTS.inc()

    # Track request start time
    start_time = time.time()

    try:
        # Process request
        response = await call_next(request)

        # Calculate latency
        latency = time.time() - start_time

        # Record metrics
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code,
        ).inc()

        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path,
        ).observe(latency)

        return response

    finally:
        # Decrement active requests
        ACTIVE_REQUESTS.dec()


def metrics_endpoint() -> FastAPIResponse:
    """
    Endpoint to expose Prometheus metrics.

    Returns metrics in Prometheus text format.
    """
    metrics = generate_latest()
    return FastAPIResponse(
        content=metrics,
        media_type=CONTENT_TYPE_LATEST,
    )


def record_query_latency(workspace_id: int, latency_seconds: float):
    """Record query processing latency."""
    QUERY_LATENCY.labels(workspace_id=str(workspace_id)).observe(latency_seconds)


def record_vector_search_latency(latency_seconds: float):
    """Record vector search latency."""
    VECTOR_SEARCH_LATENCY.observe(latency_seconds)


def record_embedding_latency(latency_seconds: float):
    """Record embedding generation latency."""
    EMBEDDING_LATENCY.observe(latency_seconds)


def record_sync_success(connector_type: str):
    """Record successful sync."""
    SYNC_SUCCESS.labels(connector_type=connector_type).inc()


def record_sync_failure(connector_type: str, error_type: str):
    """Record failed sync."""
    SYNC_FAILURE.labels(
        connector_type=connector_type,
        error_type=error_type,
    ).inc()


def record_document_ingestion(source_type: str, count: int = 1):
    """Record document ingestion."""
    DOCUMENTS_INGESTED.labels(source_type=source_type).inc(count)


def update_circuit_breaker_state(service: str, state: str):
    """
    Update circuit breaker state metric.

    Args:
        service: Service name (e.g., 'qdrant', 'openai')
        state: State ('closed', 'open', 'half_open')
    """
    state_values = {
        "closed": 0,
        "open": 1,
        "half_open": 2,
    }

    CIRCUIT_BREAKER_STATE.labels(service=service).set(state_values.get(state, 0))
