# Development Guide

This guide covers development workflows, best practices, and how to extend ContextDock.

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Adding New Connectors](#adding-new-connectors)
- [Database Migrations](#database-migrations)
- [Code Style & Quality](#code-style--quality)
- [Debugging](#debugging)
- [Performance Testing](#performance-testing)

## Development Environment Setup

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 15+
- Redis 7+
- Qdrant vector database
- Git

### Initial Setup

1. **Clone and setup virtual environment**
   ```bash
   git clone https://github.com/saurabhkashyap259/ContextDock.git
   cd ContextDock
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Start local services**
   ```bash
   docker-compose up -d postgres redis qdrant
   ```

4. **Create database**
   ```bash
   createdb contextdock  # Or use psql
   alembic upgrade head
   ```

5. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your local configuration
   ```

### Running the Application

**Terminal 1: API Server**
```bash
uvicorn src.main:app --reload --port 8000
```

**Terminal 2: Celery Worker**
```bash
celery -A src.workers.celery_app worker --loglevel=info
```

**Terminal 3: Celery Beat (scheduler)**
```bash
celery -A src.workers.celery_app beat --loglevel=info
```

Access:
- Web UI: http://localhost:8000/app
- API Docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics

## Project Structure

```
ContextDock/
├── src/
│   ├── api/                 # FastAPI routes & middleware
│   │   ├── routes/          # API endpoints
│   │   ├── middleware/      # Request middleware (metrics, logging)
│   │   └── schemas/         # Pydantic models
│   ├── connectors/          # Integration with external tools
│   │   ├── base.py          # Base connector class
│   │   ├── slack.py
│   │   ├── jira.py
│   │   └── ...
│   ├── models/              # SQLAlchemy ORM models
│   ├── services/            # Business logic
│   │   ├── query_service.py # RAG pipeline
│   │   ├── logger.py        # Structured logging
│   │   └── identity_resolution.py
│   ├── workers/             # Background tasks
│   │   ├── sync_task.py     # Document sync worker
│   │   └── celery_app.py    # Celery configuration
│   ├── ingestion/           # Document processing
│   │   ├── embeddings.py    # OpenAI embeddings
│   │   └── chunking.py      # Document chunking
│   ├── integrations/        # External service clients
│   │   └── vector_db.py     # Qdrant client
│   ├── config/              # Configuration
│   │   └── settings.py
│   ├── database.py          # Database session management
│   └── main.py              # Application entry point
├── tests/
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── conftest.py          # Pytest fixtures
├── alembic/                 # Database migrations
├── docs/                    # Documentation
└── specs/                   # Feature specifications

```

## Running Tests

### All Tests

```bash
pytest
```

### Unit Tests Only

```bash
pytest tests/unit
```

### Integration Tests

```bash
pytest tests/integration
```

### Specific Test File

```bash
pytest tests/unit/connectors/test_slack.py
```

### With Coverage

```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html  # View coverage report
```

### Performance Tests

```bash
pytest tests/integration/performance/ -v
```

### Parallel Execution

```bash
pytest -n auto  # Uses pytest-xdist
```

## Adding New Connectors

### Step 1: Create Connector Class

Create `src/connectors/your_connector.py`:

```python
"""Connector for YourService."""

from typing import List, Dict, Any, Optional
from src.connectors.base import BaseConnector


class YourServiceConnector(BaseConnector):
    """Connector for YourService integration."""
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize YourService connector.
        
        Args:
            credentials: OAuth credentials or API key
        """
        super().__init__(connector_type="your_service", credentials=credentials)
        self.api_key = credentials.get("api_key")
        # Initialize your API client here
    
    async def test_connection(self) -> bool:
        """Test if credentials are valid."""
        try:
            # Make a simple API call to verify credentials
            return True
        except Exception:
            return False
    
    async def sync_documents(
        self,
        workspace_id: int,
        last_sync_at: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch documents from YourService.
        
        Args:
            workspace_id: Workspace ID
            last_sync_at: ISO timestamp of last sync (for incremental sync)
        
        Returns:
            List of document dicts with:
            - id: Unique document ID
            - title: Document title
            - content: Full text content
            - url: Document URL
            - created_at: Creation timestamp (ISO format)
            - updated_at: Last modified timestamp
            - author: Author info dict
            - metadata: Additional metadata
            - acl: Access control list (list of user IDs/groups)
        """
        documents = []
        
        # Implement pagination
        cursor = None
        while True:
            # Fetch page of documents
            response = await self._fetch_page(cursor, last_sync_at)
            
            for item in response["items"]:
                doc = {
                    "id": item["id"],
                    "title": item["title"],
                    "content": item["content"],
                    "url": item["url"],
                    "created_at": item["created_at"],
                    "updated_at": item["updated_at"],
                    "author": {
                        "id": item["author"]["id"],
                        "name": item["author"]["name"],
                        "email": item["author"]["email"]
                    },
                    "metadata": {
                        "type": item["type"],
                        "tags": item.get("tags", [])
                    },
                    "acl": self._extract_acl(item)
                }
                documents.append(doc)
            
            # Check if more pages
            if not response.get("next_cursor"):
                break
            cursor = response["next_cursor"]
        
        return documents
    
    async def _fetch_page(self, cursor: Optional[str], modified_since: Optional[str]) -> Dict[str, Any]:
        """Fetch a page of documents from API."""
        # Implement actual API call here
        pass
    
    def _extract_acl(self, item: Dict[str, Any]) -> List[str]:
        """Extract ACL from document item."""
        # Convert connector-specific permissions to standard format
        acl = []
        
        # Example: Extract user IDs who can access this document
        if "shared_with" in item:
            acl.extend(item["shared_with"])
        
        return acl
```

### Step 2: Add OAuth Configuration

Update `src/config/settings.py`:

```python
# YourService OAuth
YOUR_SERVICE_CLIENT_ID: Optional[str] = None
YOUR_SERVICE_CLIENT_SECRET: Optional[str] = None
YOUR_SERVICE_REDIRECT_URI: Optional[str] = None
```

### Step 3: Create Unit Tests

Create `tests/unit/connectors/test_your_service.py`:

```python
"""Unit tests for YourService connector."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.connectors.your_service import YourServiceConnector


class TestYourServiceConnector:
    """Test YourService connector."""
    
    @pytest.fixture
    def connector(self):
        """Create connector instance."""
        credentials = {"api_key": "test_key"}
        return YourServiceConnector(credentials)
    
    @pytest.mark.asyncio
    async def test_connection_valid(self, connector):
        """Test connection with valid credentials."""
        result = await connector.test_connection()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_sync_documents(self, connector):
        """Test document synchronization."""
        docs = await connector.sync_documents(workspace_id=1)
        
        assert isinstance(docs, list)
        assert len(docs) > 0
        
        # Verify document structure
        doc = docs[0]
        assert "id" in doc
        assert "title" in doc
        assert "content" in doc
        assert "url" in doc
        assert "acl" in doc
```

### Step 4: Integration Testing

Create `tests/integration/connectors/test_your_service_integration.py`:

```python
"""Integration tests for YourService connector."""

import pytest
from src.connectors.your_service import YourServiceConnector


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("YOUR_SERVICE_API_KEY"),
    reason="YourService credentials not configured"
)
class TestYourServiceIntegration:
    """Integration tests with real YourService API."""
    
    @pytest.fixture
    def connector(self):
        """Create connector with real credentials."""
        credentials = {
            "api_key": os.getenv("YOUR_SERVICE_API_KEY")
        }
        return YourServiceConnector(credentials)
    
    @pytest.mark.asyncio
    async def test_real_sync(self, connector):
        """Test sync with real API."""
        docs = await connector.sync_documents(workspace_id=1)
        assert len(docs) > 0
```

### Step 5: Register Connector

Update `src/workers/sync_task.py` to include your connector:

```python
CONNECTOR_CLASSES = {
    "slack": SlackConnector,
    "jira": JiraConnector,
    "github": GitHubConnector,
    "your_service": YourServiceConnector,  # Add this
}
```

### Step 6: Add Database Migration (if needed)

```bash
alembic revision -m "Add YourService connector support"
```

## Database Migrations

### Create Migration

```bash
alembic revision -m "Add new table"
```

This creates a new migration file in `alembic/versions/`.

### Write Migration

Edit the generated file:

```python
def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        'your_table',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_table('your_table')
```

### Apply Migration

```bash
alembic upgrade head
```

### Rollback Migration

```bash
alembic downgrade -1  # Rollback one migration
```

### View History

```bash
alembic history
alembic current
```

## Code Style & Quality

### Formatting

Use Ruff for code formatting:

```bash
ruff format .
```

### Linting

```bash
ruff check .
ruff check --fix .  # Auto-fix issues
```

### Type Checking

```bash
mypy src/
```

### Pre-commit Hooks

Install pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

This automatically runs formatting and linting before each commit.

## Debugging

### VS Code Configuration

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "src.main:app",
        "--reload",
        "--port",
        "8000"
      ],
      "jinja": true
    },
    {
      "name": "Celery Worker",
      "type": "python",
      "request": "launch",
      "module": "celery",
      "args": [
        "-A",
        "src.workers.celery_app",
        "worker",
        "--loglevel=debug"
      ]
    },
    {
      "name": "Pytest",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "-v",
        "${file}"
      ]
    }
  ]
}
```

### Logging

Use structured logging with trace IDs:

```python
from src.services.logger import get_logger, bind_trace_id

logger = get_logger(__name__)

# Bind trace ID for request correlation
bind_trace_id(request.headers.get("X-Trace-ID"))

# Log with context
logger.info("processing_query", query=query, workspace_id=workspace_id)
```

### Interactive Debugging

Add breakpoints in code:

```python
import pdb; pdb.set_trace()
```

Or use IPython for better debugging:

```python
from IPython import embed; embed()
```

## Performance Testing

### Query Latency

```bash
pytest tests/integration/performance/test_query_latency.py -v
```

### Concurrent Users

```bash
pytest tests/integration/performance/test_concurrent_users.py -v
```

### Load Testing

Use Locust for load testing:

```python
# locustfile.py
from locust import HttpUser, task, between

class ContextDockUser(HttpUser):
    wait_time = between(1, 5)
    
    @task
    def query(self):
        self.client.post("/query", json={
            "query": "test query",
            "workspace_id": "workspace-1"
        })
```

Run:
```bash
locust -f locustfile.py --host=http://localhost:8000
```

### Profiling

Use `py-spy` for production profiling:

```bash
py-spy top -- python -m uvicorn src.main:app
```

Or `cProfile` for detailed profiling:

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Your code here

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

## Common Tasks

### Clear Redis Cache

```bash
redis-cli FLUSHDB
```

### Rebuild Vector Index

```python
from src.ingestion.embeddings import EmbeddingService
from src.integrations.vector_db import get_qdrant_client

# Delete and recreate collection
client = get_qdrant_client()
client.delete_collection("documents")
client.create_collection("documents", vector_size=1536)

# Re-index all documents
# (trigger sync for all connectors)
```

### Reset Database

```bash
alembic downgrade base
alembic upgrade head
```

## Troubleshooting

### Common Issues

**Import errors after adding new dependencies:**
```bash
pip install -r requirements.txt
```

**Database connection errors:**
- Check PostgreSQL is running: `pg_isready`
- Verify DATABASE_URL in .env
- Check network connectivity

**Qdrant connection errors:**
- Verify Qdrant is running: `curl http://localhost:6333/collections`
- Check QDRANT_URL in .env

**Celery worker not processing tasks:**
- Check Redis is running: `redis-cli ping`
- Verify REDIS_URL in .env
- Check worker logs for errors

## Best Practices

1. **Write tests first** (TDD approach)
2. **Use type hints** for all function signatures
3. **Log meaningful information** with context
4. **Handle errors gracefully** with circuit breakers and retries
5. **Document complex logic** with docstrings
6. **Keep functions small** (<50 lines)
7. **Use async/await** for I/O operations
8. **Cache expensive operations** (with TTL)
9. **Monitor performance** with metrics
10. **Review security implications** of changes

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [Qdrant Vector Database](https://qdrant.tech/documentation/)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
