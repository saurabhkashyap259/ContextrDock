"""FastAPI application entry point."""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.api.routes import query, conversations

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

# Include routers
app.include_router(query.router)
app.include_router(conversations.router)

# Mount static files for web UI (T185)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/app", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns basic application status and configuration info.
    """
    return {
        "status": "healthy",
        "service": "contextdock-api",
        "version": "0.1.0",
        "environment": settings.environment,
    }


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
