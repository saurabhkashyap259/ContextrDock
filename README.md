# ContextDock

**Unified search and intelligence platform for workplace tools**

ContextDock is a RAG (Retrieval-Augmented Generation) powered platform that provides unified search across all your workplace tools - Slack, Jira, Confluence, GitHub, Google Drive, and more. Get instant, context-aware answers from your entire organizational knowledge base.

## Features

- **🔍 Unified Search**: Search across all your connected tools in one place
- **🤖 AI-Powered Answers**: Get intelligent answers powered by GPT-4 and vector embeddings
- **🔐 Permission-Aware**: Respects ACLs - users only see what they're allowed to access
- **⚡ Real-time Sync**: Automatic synchronization with connected tools
- **🌐 Web Interface**: Clean, accessible web UI (WCAG 2.1 AA compliant)
- **🔌 Extensible**: Easy-to-add connector architecture for new integrations

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web UI / API                             │
│                    (FastAPI + JavaScript)                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    ┌───────────┴──────────┐
                    │                      │
         ┌──────────▼────────┐  ┌─────────▼────────┐
         │   Query Service   │  │   Sync Workers   │
         │   (RAG Pipeline)  │  │     (Celery)     │
         └──────────┬────────┘  └────────┬─────────┘
                    │                    │
      ┌─────────────┼────────────────────┼──────────────┐
      │             │                    │              │
┌─────▼──────┐ ┌───▼──────┐ ┌──────────▼────┐ ┌───────▼────────┐
│ PostgreSQL │ │  Qdrant  │ │  OpenAI API   │ │  Connectors    │
│ (Metadata) │ │ (Vectors)│ │  (Embeddings) │ │ (Slack, Jira,  │
│            │ │          │ │               │ │  GitHub, etc.) │
└────────────┘ └──────────┘ └───────────────┘ └────────────────┘
```

### Core Components

1. **FastAPI Backend** (`src/api/`)
   - RESTful API endpoints
   - Authentication & authorization
   - Query processing
   - Permission filtering

2. **Sync Workers** (`src/workers/`)
   - Celery-based background tasks
   - Connector-specific sync logic
   - Document ingestion pipeline
   - OAuth credential management

3. **Vector Database** (`src/integrations/vector_db.py`)
   - Qdrant for semantic search
   - Document embeddings storage
   - Similarity search with circuit breaker

4. **Connectors** (`src/connectors/`)
   - Slack, Jira, GitHub, Confluence, Google Drive
   - OAuth authentication
   - Incremental sync support
   - Rate limiting & error handling

5. **RAG Pipeline** (`src/services/query_service.py`)
   - Hybrid search (vector + keyword)
   - Identity resolution for ACL filtering
   - Context generation for LLM
   - Streaming responses

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Qdrant (vector database)
- OpenAI API key

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/saurabhkashyap259/ContextDock.git
   cd ContextDock
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # For development
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

   Required environment variables:
   ```bash
   # Database
   DATABASE_URL=postgresql://user:password@localhost:5432/contextdock
   
   # Redis
   REDIS_URL=redis://localhost:6379/0
   
   # Qdrant
   QDRANT_URL=http://localhost:6333
   QDRANT_API_KEY=your_qdrant_api_key
   
   # OpenAI
   OPENAI_API_KEY=sk-your-openai-api-key
   
   # OAuth Credentials (for each connector you want to enable)
   SLACK_CLIENT_ID=your_slack_client_id
   SLACK_CLIENT_SECRET=your_slack_client_secret
   JIRA_CLIENT_ID=your_jira_client_id
   JIRA_CLIENT_SECRET=your_jira_client_secret
   # ... etc
   ```

5. **Start services with Docker Compose**
   ```bash
   docker-compose up -d postgres redis qdrant
   ```

6. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

7. **Start the API server**
   ```bash
   uvicorn src.main:app --reload --port 8000
   ```

8. **Start Celery workers** (in separate terminal)
   ```bash
   celery -A src.workers.celery_app worker --loglevel=info
   ```

9. **Access the application**
   - Web UI: http://localhost:8000/app
   - API docs: http://localhost:8000/docs
   - Health check: http://localhost:8000/health

## Usage

### Connecting a Tool

1. Navigate to Settings → Integrations
2. Click "Connect" on the tool you want to add (e.g., Slack)
3. Authorize the OAuth flow
4. Wait for initial sync to complete

### Performing a Search

**Web UI:**
1. Open http://localhost:8000/app
2. Type your question in the search box
3. Get AI-powered answers with source citations

**API:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "query": "What is the status of the Q2 roadmap?",
    "workspace_id": "your-workspace-id"
  }'
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit

# Run integration tests
pytest tests/integration

# Run with coverage
pytest --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type checking
mypy src/
```

### Adding a New Connector

See [docs/development.md](docs/development.md) for detailed guide on adding new connectors.

## Deployment

See [docs/deployment.md](docs/deployment.md) for production deployment instructions, including:
- Docker setup
- Kubernetes configuration
- TLS/SSL setup
- Environment configuration
- Monitoring & alerting

## Monitoring

### Metrics

Prometheus metrics available at `/metrics`:
- `contextdock_requests_total`: Total HTTP requests by method, endpoint, status
- `contextdock_request_latency_seconds`: Request latency histogram
- `contextdock_query_latency_seconds`: RAG query latency by workspace
- `contextdock_vector_search_latency_seconds`: Vector search latency
- `contextdock_embedding_latency_seconds`: Embedding generation latency
- `contextdock_sync_success_total`: Successful syncs by connector
- `contextdock_sync_failure_total`: Failed syncs by connector and error type
- `contextdock_documents_ingested_total`: Documents ingested by source
- `contextdock_circuit_breaker_state`: Circuit breaker state (0=closed, 1=open, 2=half_open)

### Health Check

Check service health at `/health`:
```bash
curl http://localhost:8000/health
```

Returns detailed status of all services (database, Redis, Qdrant) with latency metrics.

## Data Privacy

**Important:** ContextDock does NOT use customer data to train AI models (FR-039).

- OpenAI API calls use `training_opt_out` flag
- Document content is stored securely in your infrastructure
- Vector embeddings are generated on-demand and stored in your Qdrant instance
- No customer data leaves your deployment except for API calls to OpenAI (for embeddings/completions only)

## Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork the repository** and create a feature branch
2. **Write tests** for new functionality
3. **Follow code style** (run `ruff format` and `ruff check`)
4. **Update documentation** as needed
5. **Submit a pull request** with clear description

### Code Style

- Follow PEP 8 style guidelines
- Use type hints for function signatures
- Write docstrings for public functions
- Keep functions small and focused

### Commit Messages

Follow conventional commits format:
```
feat: Add Notion connector
fix: Resolve Slack rate limit handling
docs: Update deployment guide
test: Add tests for identity resolution caching
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: [docs/](docs/)
- **Issues**: https://github.com/saurabhkashyap259/ContextDock/issues
- **Discussions**: https://github.com/saurabhkashyap259/ContextDock/discussions

## Roadmap

- [ ] Additional connectors (Notion, Microsoft 365, Dropbox)
- [ ] Advanced query features (filters, date ranges, source preferences)
- [ ] User analytics dashboard
- [ ] Custom LLM model support (Anthropic, Gemini)
- [ ] On-premise deployment guides
- [ ] Multi-tenancy support

---

Built with ❤️ using FastAPI, Qdrant, and OpenAI
