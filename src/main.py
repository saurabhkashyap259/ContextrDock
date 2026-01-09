"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.middleware.metrics import metrics_endpoint, prometheus_middleware
from src.api.routes import connectors, conversations, query, search, slack_bot
from src.config import settings

# Create FastAPI app
app = FastAPI(
    title="ContextDock API",
    description="RAG-powered unified search and intelligence platform for workplace tools",
    version="0.1.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics middleware
app.middleware("http")(prometheus_middleware)

# Include routers
app.include_router(connectors.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(slack_bot.router, prefix="/api")
app.include_router(query.router)
app.include_router(conversations.router)

# Metrics endpoint
app.get("/metrics")(metrics_endpoint)

# Mount static files for web UI (T185)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/app", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/health")
async def health_check():
    """
    Health check endpoint with service connectivity checks.

    Returns detailed status of all services:
    - Database (PostgreSQL)
    - Redis
    - Qdrant (vector database)

    Returns HTTP 200 if healthy/degraded, 503 if unhealthy.
    """
    import time
    from datetime import datetime

    from sqlalchemy import text

    from src.database import get_db
    from src.integrations.vector_db import get_qdrant_client
    from src.services.cache import get_redis_client

    services = {}
    overall_status = "healthy"

    # Check database connectivity
    try:
        start = time.time()
        db = next(get_db())
        db.execute(text("SELECT 1"))
        latency_ms = (time.time() - start) * 1000
        services["database"] = {
            "status": "up",
            "latency_ms": round(latency_ms, 2)
        }
    except Exception as e:
        services["database"] = {
            "status": "down",
            "error": str(e)
        }
        overall_status = "unhealthy"  # Database is critical

    # Check Redis connectivity
    try:
        start = time.time()
        redis_client = get_redis_client()
        redis_client.ping()
        latency_ms = (time.time() - start) * 1000
        services["redis"] = {
            "status": "up",
            "latency_ms": round(latency_ms, 2)
        }
    except Exception as e:
        services["redis"] = {
            "status": "down",
            "error": str(e)
        }
        # Redis down is degraded, not unhealthy (caching is optional)
        if overall_status == "healthy":
            overall_status = "degraded"

    # Check Qdrant connectivity
    try:
        start = time.time()
        qdrant_client = get_qdrant_client()
        # Try to list collections as a connectivity test
        qdrant_client.get_collections()
        latency_ms = (time.time() - start) * 1000
        services["qdrant"] = {
            "status": "up",
            "latency_ms": round(latency_ms, 2)
        }
    except Exception as e:
        services["qdrant"] = {
            "status": "down",
            "error": str(e)
        }
        # Qdrant down is degraded (can fall back to keyword search)
        if overall_status == "healthy":
            overall_status = "degraded"

    response_data = {
        "status": overall_status,
        "service": "contextdock-api",
        "version": "0.1.0",
        "environment": settings.app_env,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services": services
    }

    # Return 503 if unhealthy
    if overall_status == "unhealthy":
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content=response_data
        )

    return response_data


@app.get("/")
async def root():
    """Root endpoint - redirects to web UI in development."""
    if settings.is_development and (Path(__file__).parent / "static" / "index.html").exists():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/app")

    return {
        "message": "ContextDock API",
        "docs": "/docs" if settings.is_development else None,
        "web_ui": "/app" if settings.is_development else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
    )
