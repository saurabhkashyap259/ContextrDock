# Research: ContextDock RAG Platform MVP

**Date**: 2026-01-06  
**Purpose**: Resolve technical unknowns and document best practices for technology choices

## Vector Database Selection

**Decision**: Qdrant as default, with pluggable interface supporting Weaviate and pgvector

**Rationale**:
- **Qdrant**: Open-source, excellent performance for similarity search, native Python SDK, supports filtering (critical for ACL enforcement), easy Docker deployment
- **Weaviate**: Alternative for larger scale deployments, strong schema support
- **pgvector**: Simplest option using existing PostgreSQL, reduces infrastructure complexity but lower performance at scale

**Alternatives Considered**:
- **Pinecone/Milvus**: Excluded - Pinecone is cloud-only (violates self-hosted requirement), Milvus has steeper learning curve
- **Chroma**: Excluded - Less mature for production workloads, weaker filtering capabilities
- **FAISS**: Excluded - No built-in persistence or server, requires custom wrapper

**Best Practices**:
- Use collections per workspace for isolation
- Store ACL metadata as payload for query-time filtering
- Implement connection pooling for concurrent query handling
- Use batch operations for embedding ingestion (100-500 vectors per batch)
- Monitor index size and consider re-indexing strategy for growing datasets

## Embedding Model Selection

**Decision**: OpenAI text-embedding-3-small as default, configurable via environment

**Rationale**:
- Cost-effective ($0.02/1M tokens vs $0.10/1M for ada-002)
- 1536 dimensions (same as ada-002), good for hybrid search
- Strong performance on retrieval benchmarks
- Wide deployment base (proven in production)

**Alternatives Considered**:
- **text-embedding-3-large**: Better quality but 3x cost, overkill for MVP
- **Cohere embed-v3**: Competitive quality, good alternative for non-OpenAI users
- **Local models (sentence-transformers)**: BAAI/bge-large-en-v1.5 or intfloat/e5-large-v2 for fully self-hosted deployments

**Best Practices**:
- Cache embeddings with content hash to avoid regeneration
- Use async batch processing for large document sets
- Implement retry with exponential backoff for API calls
- Monitor embedding API latency and implement circuit breaker for failures
- Store embedding model version with each vector for migration tracking

## Hybrid Search Architecture

**Decision**: BM25 (sparse) + vector similarity (dense) with reciprocal rank fusion (RRF)

**Rationale**:
- BM25 excels at exact keyword/term matching (e.g., "PR-1234", "bug-fix")
- Vector similarity captures semantic meaning and synonyms
- RRF combines rankings without needing score normalization
- Industry-proven approach (used by Elasticsearch, OpenSearch)

**Alternatives Considered**:
- **Vector-only**: Misses exact matches, struggles with entity names/IDs
- **Keyword-only**: Poor semantic understanding, synonym problems
- **Weighted linear combination**: Requires tuning, scores not comparable across methods

**Best Practices**:
- Implement BM25 using PostgreSQL full-text search or Elasticsearch
- Retrieve top-K from each method (K=20-50), merge with RRF
- Apply ACL filtering AFTER retrieval from both paths
- Re-rank final candidates with cross-encoder if latency budget allows
- Log retrieval metrics (recall@K, precision) for continuous improvement

## Connector SDK Design

**Decision**: Abstract base class with plugin discovery, standardized lifecycle hooks

**Rationale**:
- ABC pattern familiar to Python developers
- Lifecycle hooks (init, validate, sync, fetch_page, extract_acl) handle common patterns
- Plugin discovery via entry points enables drop-in connectors
- Shared utilities (OAuth, pagination, rate limiting) reduce boilerplate

**Best Practices**:
- Define clear interface: `ConnectorBase.sync()` returns `Iterator[Document]`
- Use async/await for I/O-bound connector operations
- Implement cursor-based pagination state in `SyncRun.cursor_state_json`
- Provide OAuth2 helper for standard flows (authorization code, client credentials)
- Include rate limiter decorator (`@rate_limit(calls=100, per=60)`) for connector methods
- Document expected ACL metadata format for each connector type
- Ship example connector (`examples/custom_connector.py`) with full implementation

## Chunking Implementation

**Decision**: LangChain RecursiveCharacterTextSplitter with custom separators

**Rationale**:
- Respects document structure (paragraphs, sentences, words)
- Configurable chunk size (500-1000 tokens) and overlap (100 tokens)
- Battle-tested in production RAG systems
- Handles multiple document types with custom separator lists

**Best Practices**:
- Token counting with tiktoken (matches OpenAI's tokenizer)
- Custom separators per document type:
  - Markdown: `["\\n## ", "\\n### ", "\\n\\n", "\\n", " "]`
  - Code: `["\\n\\nclass ", "\\n\\ndef ", "\\n\\n", "\\n", " "]`
  - Plain text: `["\\n\\n", "\\n", ". ", " "]`
- Store original document_id and chunk_index for citation reconstruction
- Include surrounding context in chunk metadata for better answer generation

## Identity Resolution Strategy

**Decision**: Email-based automatic matching with manual override table

**Rationale**:
- Email is universal identifier across workplace tools
- Reduces admin burden (automatic for 95% of users)
- Override table handles edge cases (different emails, service accounts, contractors)

**Best Practices**:
- Normalize emails (lowercase, trim whitespace) before matching
- Store per-connector identity mappings: `user_id → {slack_user_id, jira_account_id, github_login}`
- API endpoint for admin to view/edit identity mappings
- Log identity resolution failures for admin review
- Support OAuth user info endpoints to fetch email from each connector
- Cache resolved identities with TTL (1 hour) to reduce lookup overhead

## Sync Schedule Implementation

**Decision**: Celery Beat for scheduled tasks, one beat schedule per connector

**Rationale**:
- Celery is Python standard for distributed task queues
- Beat scheduler supports per-task cron expressions
- Scales horizontally with multiple workers
- Redis backend provides persistence and monitoring

**Best Practices**:
- Store schedule in database (dynamic), sync to Celery Beat on connector update
- Smart defaults: Slack (hourly), Jira/Confluence (every 6 hours), GitHub/Dropbox (daily), Figma (daily)
- Use priority queues (high priority for manual "sync now", low for scheduled)
- Implement task timeout (30 min for sync tasks)
- Store task_id in SyncRun for status tracking and cancellation
- Graceful shutdown: allow current sync to complete, no new syncs during deploy

## Write-back Action Preview

**Decision**: JSON schema + React form renderer with diff view for updates

**Rationale**:
- JSON schema defines structure declaratively (fields, types, validation)
- Generic form renderer eliminates per-action UI code
- Diff view (before/after) for updates uses `jsondiffpatch` library
- In-memory preview (no database writes) until approval

**Best Practices**:
- Define schema per action type: `CreateJiraTicketSchema`, `CreateConfluencePageSchema`
- Validate preview data against schema before showing to user
- Store preview data in `AgentAction.preview_json` (encrypted if contains sensitive data)
- Implement approval expiration (1 hour) to prevent stale actions
- Dry-run execution: test permissions before showing preview
- Audit log includes full preview + actual result for transparency

## Authentication & Authorization

**Decision**: JWT tokens for API auth, OAuth2 for connector credentials

**Rationale**:
- JWT stateless, scales horizontally, standard in FastAPI
- OAuth2 delegated authorization to avoid storing passwords
- Scoped tokens per connector minimize blast radius

**Best Practices**:
- Store connector credentials encrypted at rest (Fernet symmetric encryption, key in env)
- Use short-lived JWT access tokens (15 min) + refresh tokens (7 days)
- Implement token rotation on refresh
- Request minimal OAuth scopes (read-only for connectors, write for actions)
- Support OAuth2 PKCE flow for enhanced security
- Log all token issuance and refresh events for audit

## Testing Strategy

**Decision**: Pytest with fixtures, mocked connectors for integration tests, VCR.py for API recordings

**Rationale**:
- Pytest fixtures provide clean test setup (database, test users, connectors)
- Mocked connectors enable testing without real API credentials
- VCR.py records real API responses for contract tests without live calls

**Best Practices**:
- Unit tests: Fast, isolated, no external dependencies (80% of tests)
- Integration tests: Real database (PostgreSQL test instance), mocked external APIs (15% of tests)
- Contract tests: VCR.py cassettes from real API calls, updated quarterly (5% of tests)
- Use `pytest-asyncio` for async test functions
- Fixtures in `tests/conftest.py`: `db_session`, `test_user`, `mock_connector`, `vector_db_client`
- Coverage target: 80% minimum, 90% goal
- Run fast tests in CI on every commit, slow tests (contract) nightly

## Deployment Architecture

**Decision**: Docker Compose for quickstart, Kubernetes manifests for production

**Rationale**:
- Docker Compose: Single-command setup for developers and small deployments
- Kubernetes: Production-grade orchestration, auto-scaling, health checks

**Services in Docker Compose**:
- `api`: FastAPI application (ports 8000)
- `postgres`: PostgreSQL 15 (metadata)
- `qdrant`: Qdrant vector database (ports 6333)
- `redis`: Redis (queue/cache)
- `celery-worker`: Background task processor
- `celery-beat`: Scheduled task scheduler
- `slack-bot`: Slack bot listener (optional, same codebase as api)

**Best Practices**:
- Use health check endpoints (`/health`, `/ready`) for container orchestration
- Implement graceful shutdown (SIGTERM handling, finish in-flight requests)
- Environment-based configuration (12-factor app)
- Separate secrets from config (Docker secrets, Kubernetes secrets)
- Resource limits: API (512MB-1GB), Celery (1-2GB), Postgres (2GB), Qdrant (4GB)
- Persistent volumes for postgres data, qdrant storage
- Backup strategy: Daily postgres dumps, qdrant snapshots

## Monitoring & Observability

**Decision**: Structured logging (JSON), Prometheus metrics, OpenTelemetry traces

**Rationale**:
- Structured logs enable parsing and filtering (e.g., all errors for connector X)
- Prometheus standard for metrics, integrates with Grafana
- OpenTelemetry for distributed tracing across services

**Best Practices**:
- Use Python `structlog` for structured logging
- Log levels: DEBUG (development), INFO (production), ERROR (always)
- Key metrics: query latency (p50/p95/p99), connector sync success rate, embedding generation time, cache hit rate
- Trace IDs in all logs for request correlation
- Dashboard panels: Query volume over time, error rate by endpoint, sync job status, vector DB size
- Alerts: Error rate >5%, API latency >10s, sync failures >3 consecutive

## Summary

All technical decisions align with constitution principles:
- ✅ TDD-ready: All components have clear interfaces for testing
- ✅ .venv isolation: Standard Python project structure
- ✅ Type safety: All libraries support type hints
- ✅ Pytest: Testing strategy defined
- ✅ Quality: ruff + mypy tooling standard across ecosystem
- ✅ Dependencies: All choices are well-maintained, pinned versions in requirements.txt
- ✅ Simplicity: Industry-standard patterns, avoid premature optimization

No blocking unknowns remain. Ready to proceed to Phase 1 (data model + contracts).
