# Multi-stage Dockerfile for ContextDock
# Stage 1: Build - compile dependencies
# Stage 2: Test - run tests
# Stage 3: Production - minimal runtime image

# ============================================================================
# Stage 1: Build
# ============================================================================
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================================
# Stage 2: Test
# ============================================================================
FROM python:3.11-slim as test

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Copy dev requirements and install test dependencies
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# Make sure scripts are in PATH
ENV PATH=/root/.local/bin:$PATH

# Run tests
RUN pytest tests/unit --tb=short

# Lint code
RUN ruff check src/

# Type check
RUN mypy src/ --ignore-missing-imports || true

# ============================================================================
# Stage 3: Production
# ============================================================================
FROM python:3.11-slim as production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r contextdock && useradd -r -g contextdock contextdock

# Copy installed packages from builder to user's local directory
COPY --from=builder --chown=contextdock:contextdock /root/.local /home/contextdock/.local

# Copy application code
COPY --chown=contextdock:contextdock . .

# Make sure scripts are in PATH
ENV PATH=/home/contextdock/.local/bin:$PATH

# Set Python environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Switch to non-root user
USER contextdock

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose.yml)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
