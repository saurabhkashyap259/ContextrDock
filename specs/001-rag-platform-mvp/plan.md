# Implementation Plan: ContextDock RAG Platform MVP

**Branch**: `001-rag-platform-mvp` | **Date**: 2026-01-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-rag-platform-mvp/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build an open-source, self-hostable RAG + Agentic AI platform that connects to workplace tools (Slack, Jira, Confluence, GitHub, Figma, Dropbox), answers employee questions with citations and deep links, and safely creates/updates content via human-approved actions. The platform uses hybrid retrieval (keyword + vector), permission-aware access control, and a Connector SDK for extensibility. Primary interfaces are web chat and Slack bot. Technical approach: Python-based microservices with FastAPI, PostgreSQL for metadata, vector database for embeddings, Redis for queue/cache, and pluggable LLM backends.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI (API framework), Pydantic (data validation), SQLAlchemy (ORM), Qdrant/Weaviate/pgvector (vector database), OpenAI/Anthropic SDKs (LLM), LangChain (RAG orchestration), pytest (testing)  
**Storage**: PostgreSQL (metadata, users, connectors, audit logs), Vector DB (embeddings), Redis (job queue, caching), S3-compatible storage (file uploads, attachments)  
**Testing**: pytest with fixtures, pytest-asyncio for async tests, coverage.py for coverage reports, contract tests against mock connector APIs  
**Target Platform**: Linux server (Docker containers), deployable via Docker Compose for quickstart, Kubernetes-ready for production  
**Project Type**: Single backend project with web API + Slack bot  
**Performance Goals**: <10s query response (95th percentile), handle 50 concurrent users, sync 10k documents in <5 minutes, permission checks <100ms  
**Constraints**: 80% test coverage minimum, zero unauthorized data access, all write actions require approval, fail closed on ACL uncertainty, TLS required  
**Scale/Scope**: MVP supports 100k documents, 50 concurrent users, 6 connectors (Slack/Jira/Confluence/GitHub/Figma/Dropbox), single workspace

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Strict TDD** | ✅ PASS | All acceptance criteria in spec.md will be converted to pytest tests before implementation. Red-Green-Refactor cycle enforced. |
| **II. Virtual Environment (.venv)** | ✅ PASS | Project will use .venv for all dependencies. .gitignore will exclude .venv/. |
| **III. Type Safety & Static Analysis** | ✅ PASS | All Python code will have type hints. mypy in strict mode will be enforced in CI/CD. |
| **IV. Pytest Testing Framework** | ✅ PASS | Tests organized in tests/unit/, tests/integration/, tests/contract/. 80% coverage minimum. |
| **V. Code Quality & Formatting** | ✅ PASS | ruff will be used for linting and formatting. 100-char line limit. Docstrings for public APIs. |
| **VI. Dependency Management** | ✅ PASS | requirements.txt with pinned versions. requirements-dev.txt for dev deps. New deps will be justified. |
| **VII. Simplicity & YAGNI** | ✅ PASS | MVP scope clearly defined. Out-of-scope items deferred (SSO, real-time webhooks, multi-tenancy). |

**Overall**: ✅ ALL GATES PASS - Ready to proceed to Phase 0 research.

### Post-Phase 1 Re-evaluation (2026-01-06)

*After completing research.md, data-model.md, api-spec.yaml, and quickstart.md:*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Strict TDD** | ✅ PASS | Data model and API contracts provide clear test targets. Contract tests will use VCR.py cassettes. Integration tests cover end-to-end flows. |
| **II. Virtual Environment (.venv)** | ✅ PASS | Quickstart.md documents .venv setup. Docker Compose isolates services. No violations in design. |
| **III. Type Safety & Static Analysis** | ✅ PASS | SQLAlchemy models use type hints. Pydantic schemas enforce runtime validation. FastAPI generates OpenAPI spec from types. |
| **IV. Pytest Testing Framework** | ✅ PASS | Quickstart.md includes pytest examples. Test structure (unit/integration/contract) defined. Coverage target maintained at 80%. |
| **V. Code Quality & Formatting** | ✅ PASS | All design artifacts follow markdown conventions. Code examples use ruff-compatible formatting. No deviations from 100-char limit. |
| **VI. Dependency Management** | ✅ PASS | Research.md justifies all technology choices (FastAPI, SQLAlchemy, Qdrant, LangChain, pytest). Pinned versions planned in requirements.txt. |
| **VII. Simplicity & YAGNI** | ✅ PASS | Design follows MVP scope strictly. No premature optimization (e.g., single workspace, simple JWT auth). Plugin system (Connector SDK) enables future growth without bloat. |

**Overall**: ✅ ALL GATES PASS - Constitution principles upheld through Phase 1 design. Ready for Phase 2 (/speckit.tasks).

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── connectors/              # Connector SDK + implementations
│   ├── sdk/                 # Base classes, interfaces, common patterns
│   ├── slack/               # Slack connector
│   ├── jira/                # Jira connector
│   ├── confluence/          # Confluence connector
│   ├── github/              # GitHub connector
│   ├── figma/               # Figma connector
│   └── dropbox/             # Dropbox connector
├── ingestion/               # Document processing, chunking, embedding
├── retrieval/               # Hybrid search, ACL filtering, re-ranking
├── models/                  # SQLAlchemy models (User, Connector, Document, etc.)
├── api/                     # FastAPI routes and schemas
│   ├── routes/              # Endpoint handlers (query, connectors, admin, actions)
│   └── middleware/          # Auth, logging, error handling
├── agents/                  # Write-back action handlers
├── services/                # Business logic (auth, identity resolution, permissions)
├── integrations/            # Slack bot, LLM clients, vector DB clients
└── config/                  # Settings, environment management

tests/
├── unit/                    # Unit tests for individual modules
├── integration/             # Integration tests for end-to-end flows
└── contract/                # Contract tests for connector APIs

.venv/                       # Virtual environment (excluded from git)
requirements.txt             # Production dependencies with pinned versions
requirements-dev.txt         # Development dependencies
pyproject.toml               # Project metadata, tool configuration (ruff, mypy)
docker-compose.yml           # Docker Compose for local deployment
Dockerfile                   # Container image definition
.gitignore                   # Exclude .venv/, __pycache__, *.pyc, etc.
```

**Structure Decision**: Single Python project structure selected. This is a backend-only service with API endpoints. Web UI and Slack bot are different client interfaces to the same API. No separate frontend/ directory needed for MVP - web UI can be simple HTML/JS served from FastAPI static files or built separately later. Focus is on robust API + connector architecture.

## Implementation Guidance

### Critical Requirements Implementation

**Fail-Closed ACL Behavior (FR-038)**:
- When `acl_json` is NULL, empty, or malformed for a DocumentChunk, the chunk MUST NOT be returned in query results
- Implement validation: `if not chunk.acl_json or 'allowed_user_ids' not in chunk.acl_json: continue`
- Log all fail-closed events for audit: `logger.warning("ACL undefined for chunk {chunk_id}, excluding from results")`
- Never assume default permissions; explicit ACL required for every chunk

**Graceful Degradation (FR-047)**:
- When Qdrant/vector DB is unavailable, automatically fall back to PostgreSQL full-text search (keyword-only)
- Implement circuit breaker pattern: after 3 consecutive vector DB failures, switch to degraded mode for 5 minutes
- Return metadata in response indicating degraded mode: `{"search_mode": "keyword_only", "vector_db_unavailable": true}`
- Log degradation events and alert monitoring system

**OAuth Scope Requirements (FR-037, Connector entity)**:
- **Slack**: `channels:read`, `channels:history`, `users:read` (read-only)
- **Jira**: `read:jira-work`, `read:jira-user` (no write permissions)
- **Confluence**: `read:confluence-content.all`, `read:confluence-space.summary`
- **GitHub**: `repo:read`, `user:read` (public repos only for MVP, private repos require explicit scope)
- **Figma**: `file:read` (view files and comments)
- **Dropbox**: `files.metadata.read`, `files.content.read`
- Document these in ConnectorDefinition.config_schema for each type

**Connector Credential Expiration Handling (Edge Case, CHK039)**:
- Detect OAuth token expiration via 401 responses from connector APIs
- Implement automatic token refresh using stored refresh_token if available
- If refresh fails, mark Connector status='error', set last_error, and notify admin
- Implement retry with exponential backoff: 1min, 5min, 15min, then stop
- Admin UI shows "Re-authorize" button for expired connectors

**Document Deletion Tracking (Edge Case, CHK040)**:
- During incremental sync, compare current source documents with previously synced documents
- Documents no longer returned by source API are marked as deleted (soft delete with deleted_at timestamp)
- Deleted documents trigger cascade deletion of DocumentChunks and vector DB cleanup
- Preserve Document metadata in archive table for audit trail (30-day retention)

**Embedding Generation Failure Handling (Edge Case, CHK041)**:
- Catch OpenAI API errors during embedding generation (content too long, rate limit, service error)
- For content >8191 tokens, truncate to fit model limit, log warning
- For rate limits, implement exponential backoff with jitter: 1s, 2s, 4s, 8s
- For persistent failures, skip chunk, log error, continue processing remaining chunks
- Track failed embeddings in SyncRun.error_summary for admin visibility

**Action Preview Expiration (CHK080)**:
- AgentAction.expires_at set to 1 hour after creation by default
- Cleanup job runs hourly, sets status='expired' for drafts past expires_at
- When user attempts to approve expired action, return 409 Conflict: "Preview expired, please regenerate"
- No grace period; expiration is strict to prevent stale data

**Multiple Identity Mappings Handling (CHK079)**:
- User.connector_identities is a flat dict: `{"slack": "U123", "jira": "account-id"}`
- If multiple Slack user IDs match a single email during sync, use the first match, log ambiguity warning
- Admin can manually override via `/v1/admin/users/{id}/identity-mappings` endpoint
- System prefers explicitly set mappings over auto-matched mappings

**Infrastructure Requirements (FR-046)**:
- **Minimum (Quickstart)**: 2 CPU cores, 4GB RAM, 20GB disk (SSD recommended)
  - API + Celery Worker: 1GB
  - PostgreSQL: 1GB
  - Qdrant: 1.5GB
  - Redis: 256MB
  - OS + overhead: 250MB
- **Production (50 concurrent users)**: 4 CPU cores, 8GB RAM, 100GB disk
  - API (2 replicas): 2GB
  - Celery Workers (2): 2GB
  - PostgreSQL: 2GB
  - Qdrant: 2GB
  - Redis: 512MB
- Network: 100 Mbps minimum, 1 Gbps recommended for large file syncs

**Accessibility Implementation (FR-048-050)**:
- Keyboard navigation: All buttons and links must be focusable with Tab, activatable with Enter/Space
- Skip links: Provide "Skip to main content" for screen readers
- ARIA labels:
  - `<button aria-label="Expand citation from Confluence">` for citation links
  - `<div role="status" aria-live="polite">` for query result loading
  - `<nav aria-label="Main navigation">` for top nav
- Color contrast: Test all text/background combinations with WAVE or axe DevTools, ensure 4.5:1 minimum
- Focus indicators: Visible 2px outline on focused elements, distinct from non-focused state

### Testing Strategy Details

**Contract Test Coverage**:
- Record VCR.py cassettes for each connector type: `tests/contract/cassettes/slack_sync.yaml`
- Test scenarios: successful sync, rate limit response, auth failure, partial data
- Update cassettes quarterly or when connector API versions change
- Never commit credentials; sanitize tokens in cassettes with placeholder values

**Integration Test Fixtures**:
- `db_session`: Fresh PostgreSQL database for each test class, auto-rollback after test
- `test_user`: User with known email, connector_identities pre-populated
- `mock_connector`: Connector with fake credentials, status='active', returns test documents
- `vector_db_client`: Qdrant client connected to test collection, auto-cleanup
- `celery_app`: Celery with eager mode (synchronous execution) for deterministic tests

**Performance Test Scenarios**:
- Query latency: 1000 requests with 10 concurrent users, measure p50/p95/p99
- Sync throughput: Index 10k test documents, measure time to completion
- ACL filtering: Query with 1000 chunks, 500 filtered by ACL, measure overhead
- Concurrent users: 50 simultaneous queries, measure response time degradation

---

**Phase 1 Complete**: All planning artifacts generated, implementation guidance documented. Ready for `/speckit.tasks`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. All constitution principles are satisfied by the technical approach.
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
