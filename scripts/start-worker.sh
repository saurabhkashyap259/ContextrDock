#!/bin/bash
#
# Start Celery Worker
#
# This script starts a Celery worker for processing background tasks.
# Workers handle message sync, document indexing, and other async operations.
#

set -e

# Change to project root (parent of scripts/)
cd "$(dirname "$0")/.."

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ Virtual environment not found. Run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Set environment
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Default concurrency (can be overridden)
CONCURRENCY=${CELERY_CONCURRENCY:-4}

# Worker name (can be overridden)
WORKER_NAME=${CELERY_WORKER_NAME:-"worker1"}

# Log level
LOG_LEVEL=${CELERY_LOG_LEVEL:-"INFO"}

echo "🚀 Starting Celery Worker..."
echo "   Name: ${WORKER_NAME}"
echo "   Concurrency: ${CONCURRENCY}"
echo "   Log Level: ${LOG_LEVEL}"
echo ""

# Start worker
celery -A src.workers.celery_app worker \
    --loglevel="${LOG_LEVEL}" \
    --concurrency="${CONCURRENCY}" \
    --hostname="${WORKER_NAME}@%h" \
    --max-tasks-per-child=100 \
    --time-limit=3600 \
    --soft-time-limit=3300
