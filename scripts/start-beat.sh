#!/bin/bash
#
# Start Celery Beat Scheduler
#
# This script starts Celery Beat for scheduling periodic tasks.
# Beat handles automated syncs based on connector schedules.
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

# Log level
LOG_LEVEL=${CELERY_LOG_LEVEL:-"INFO"}

echo "⏰ Starting Celery Beat Scheduler..."
echo "   Log Level: ${LOG_LEVEL}"
echo ""

# Start beat scheduler
celery -A src.workers.celery_app beat \
    --loglevel="${LOG_LEVEL}" \
    --pidfile=/tmp/celerybeat.pid \
    --schedule=/tmp/celerybeat-schedule
