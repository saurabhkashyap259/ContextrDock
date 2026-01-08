# Tasks: ContextDock RAG Platform MVP

**Branch**: `001-rag-platform-mvp`  
**Date**: 2026-01-07  
**Input**: Design documents from `/specs/001-rag-platform-mvp/`

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. Following strict TDD: tests written first (Red), then implementation (Green), then refactor.

**Format**: `- [ ] [TaskID] [P?] [Story?] Description with file path`
- **[P]**: Parallelizable (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (US1, US2, US3, US4, US5, US6)

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Initialize Python project structure, dependencies, and development environment

**Duration Estimate**: 2-3 hours

### Tasks

- [X] T001 Create Python project structure per plan.md (src/, tests/, .venv/, requirements.txt, pyproject.toml)
- [X] T002 [P] Initialize .venv virtual environment and install base dependencies (Python 3.11+)
- [X] T003 [P] Configure ruff in pyproject.toml (line-length=100, target-version=py311)
- [X] T004 [P] Configure mypy in pyproject.toml (strict=true, warn_return_any=true)
- [X] T005 [P] Create .gitignore with .venv/, __pycache__/, *.pyc, .pytest_cache/, htmlcov/
- [X] T006 [P] Set up pytest configuration in pyproject.toml (testpaths, asyncio_mode=auto)
- [X] T007 [P] Create docker-compose.yml with services: postgres, redis, qdrant
- [X] T008 [P] Create .env.example with all required environment variables (DATABASE_URL, REDIS_URL, QDRANT_URL, OPENAI_API_KEY, ANTHROPIC_API_KEY, OLLAMA_BASE_URL, SECRET_KEY, FERNET_KEY)
- [X] T009 [P] Create src/config/settings.py using Pydantic Settings for env management
- [X] T010 [P] Create tests/conftest.py with pytest fixtures (db_session, test_user, mock_connector)

**Independent Test**: Run `pytest tests/` (should pass with empty test suite), verify `ruff check src/` and `mypy src/` pass with no errors.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database models, authentication, and core utilities needed by all user stories

**Duration Estimate**: 8-10 hours

### Tasks

- [X] T011 Create Alembic migration setup in alembic/ directory with env.py and alembic.ini
- [X] T012 Write test for Workspace model in tests/unit/models/test_workspace.py
- [X] T013 Implement Workspace model in src/models/workspace.py (id, name, created_at, updated_at)
- [X] T014 [P] Write test for User model in tests/unit/models/test_user.py
- [X] T015 [P] Implement User model in src/models/user.py (email, role, connector_identities JSONB)
- [X] T016 [P] Write test for ConnectorDefinition model in tests/unit/models/test_connector_definition.py
- [X] T017 [P] Implement ConnectorDefinition model in src/models/connector_definition.py
- [X] T018 Create Alembic migration: Phase 2 foundational entities (Workspace, User, ConnectorDefinition - 3 entities)
- [X] T019 Write test for JWT token generation/validation in tests/unit/services/test_auth.py
- [X] T020 Implement JWT auth service in src/services/auth.py (15min access, 7day refresh tokens)
- [X] T021 [P] Write test for auth middleware in tests/unit/api/middleware/test_auth.py
- [X] T022 [P] Implement auth middleware in src/api/middleware/auth.py (Bearer token validation)
- [X] T023 [P] Write test for Fernet encryption utility in tests/unit/services/test_encryption.py
- [X] T024 [P] Implement encryption utility in src/services/encryption.py (for connector credentials)
- [X] T025 Create FastAPI app skeleton in src/main.py with /health endpoint
- [X] T026 [P] Write integration test for /health endpoint in tests/integration/api/test_health.py

**Independent Test**: Start Docker Compose, run Alembic migrations, verify database tables exist, call /health endpoint returns 200.

---

## Phase 3: User Story 1 - Ask Questions Across Connected Tools (P1)

**Goal**: Users can ask natural language questions and receive answers with citations and deep links

**Independent Test**: Index sample Confluence documents, query "What is our API strategy?", verify answer includes citations with working URLs

**Duration Estimate**: 16-20 hours

### Database Models (US1)

- [X] T027 Write test for Document model in tests/unit/models/test_document.py
- [X] T028 Implement Document model in src/models/document.py (source_type, source_id, title, url, content_hash)
- [X] T029 [P] Write test for DocumentChunk model in tests/unit/models/test_document_chunk.py
- [X] T030 [P] Implement DocumentChunk model in src/models/document_chunk.py (content, token_count, embedding_id, acl_json)
- [X] T031 [P] Write test for Conversation model in tests/unit/models/test_conversation.py
- [X] T032 [P] Implement Conversation model in src/models/conversation.py (channel_type, external_channel_id)
- [X] T033 [P] Write test for Message model in tests/unit/models/test_message.py
- [X] T034 [P] Implement Message model in src/models/message.py (role, content, citations_json)
- [X] T035 Create Alembic migration: Phase 3 US1 entities (Document, DocumentChunk, Conversation, Message - 4 entities)

### Ingestion Pipeline (US1)

- [X] T036 Write test for chunker in tests/unit/ingestion/test_chunker.py (500-1000 tokens, 100 overlap)
- [X] T037 Implement chunker in src/ingestion/chunker.py using LangChain RecursiveCharacterTextSplitter
- [X] T038 [P] Write test for embedding service in tests/unit/ingestion/test_embeddings.py
- [X] T039 [P] Implement embedding service in src/ingestion/embeddings.py (OpenAI text-embedding-3-small)
- [X] T040 [P] Write test for Qdrant client wrapper in tests/unit/integrations/test_vector_db.py (test abstract VectorDB interface)
- [X] T041 [P] Implement vector DB client in src/integrations/vector_db.py (abstract VectorDB base class + Qdrant/Weaviate/pgvector implementations for pluggable backends per FR-043)
- [X] T042 Write test for document ingestion pipeline in tests/unit/ingestion/test_pipeline.py
- [X] T043 Implement ingestion pipeline in src/ingestion/pipeline.py (chunk → embed → store in Qdrant + PostgreSQL)

### Retrieval Engine (US1)

- [X] T044 Write test for BM25 keyword search in tests/unit/retrieval/test_keyword_search.py
- [X] T045 Implement keyword search in src/retrieval/keyword_search.py (PostgreSQL full-text search)
- [X] T046 [P] Write test for vector similarity search in tests/unit/retrieval/test_vector_search.py
- [X] T047 [P] Implement vector search in src/retrieval/vector_search.py (Qdrant query with filters)
- [X] T048 Write test for hybrid search with RRF in tests/unit/retrieval/test_hybrid_search.py
- [X] T049 Implement hybrid search in src/retrieval/hybrid_search.py (BM25 + vector, reciprocal rank fusion)
- [X] T050 [P] Write test for ACL filtering in tests/unit/retrieval/test_acl_filter.py (fail-closed behavior)
- [X] T051 [P] Implement ACL filter in src/retrieval/acl_filter.py (check user permissions, exclude undefined ACLs)
- [X] T052 [P] Write test for identity resolution in tests/unit/services/test_identity_resolution.py
- [X] T053 [P] Implement identity resolution in src/services/identity_resolution.py (email-based matching)

### LLM Integration (US1)

- [X] T054 Write test for OpenAI client wrapper in tests/unit/integrations/test_llm_client.py (test abstract LLMClient interface)
- [X] T055 Implement LLM client in src/integrations/llm_client.py (abstract LLMClient base class + OpenAI/Anthropic/Ollama implementations for pluggable backends per FR-042)
- [X] T056 [P] Write test for answer generation in tests/unit/retrieval/test_answer_generation.py
- [X] T057 [P] Implement answer generation in src/retrieval/answer_generation.py (RAG with grounded citations)

### API Endpoints (US1)

- [X] T058 Write test for POST /v1/query endpoint in tests/integration/api/test_query.py
- [X] T059 Implement POST /v1/query in src/api/routes/query.py (question → retrieval → LLM → citations)
- [X] T060 [P] Write test for GET /v1/conversations endpoint in tests/integration/api/test_conversations.py
- [X] T061 [P] Implement GET /v1/conversations in src/api/routes/conversations.py
- [X] T062 [P] Write test for GET /v1/conversations/{id}/messages in tests/integration/api/test_conversation_messages.py
- [X] T063 [P] Implement GET /v1/conversations/{id}/messages in src/api/routes/conversations.py
- [X] T064 Create Pydantic schemas in src/api/schemas/query.py (QueryRequest, QueryResponse, Citation, Message)

### Integration Tests (US1)

- [X] T065 Write end-to-end test for US1 Scenario 1 in tests/integration/scenarios/test_us1_scenario1.py (single source citation)
- [X] T066 Write end-to-end test for US1 Scenario 2 in tests/integration/scenarios/test_us1_scenario2.py (multi-source synthesis)
- [X] T067 Write end-to-end test for US1 Scenario 3 in tests/integration/scenarios/test_us1_scenario3.py (insufficient evidence)
- [X] T068 Write end-to-end test for US1 Scenario 4 in tests/integration/scenarios/test_us1_scenario4.py (last indexed timestamp)

---

## Phase 4: User Story 2 - Connect and Sync Workplace Tools (P1)

**Goal**: Administrators can securely connect workplace tools and sync data with configurable schedules

**Independent Test**: Add Jira connector, configure projects, run manual sync, verify issues appear in database with correct metadata

**Duration Estimate**: 20-24 hours

### Database Models (US2)

- [X] T069 Write test for Connector model in tests/unit/models/test_connector.py
- [X] T070 Implement Connector model in src/models/connector.py (type, config_json, credentials_encrypted, sync_schedule)
- [X] T071 [P] Write test for SyncRun model in tests/unit/models/test_sync_run.py
- [X] T072 [P] Implement SyncRun model in src/models/sync_run.py (status, documents_added/updated/deleted, cursor_state_json)
- [X] T073 Create Alembic migration: Phase 4 US2 entities (Connector, SyncRun - 2 entities)

### Connector SDK (US2)

- [X] T074 Write test for ConnectorBase abstract class in tests/unit/connectors/sdk/test_base.py
- [X] T075 Implement ConnectorBase in src/connectors/sdk/base.py (lifecycle hooks: sync, fetch_page, extract_acl)
- [X] T076 [P] Write test for OAuth2 helper in tests/unit/connectors/sdk/test_oauth.py
- [X] T077 [P] Implement OAuth2 helper in src/connectors/sdk/oauth.py (authorization flow, token refresh)
- [X] T078 [P] Write test for rate limiter decorator in tests/unit/connectors/sdk/test_rate_limiter.py
- [X] T079 [P] Implement rate limiter in src/connectors/sdk/rate_limiter.py (@rate_limit decorator)
- [X] T080 [P] Write test for pagination helper in tests/unit/connectors/sdk/test_pagination.py
- [X] T081 [P] Implement pagination helper in src/connectors/sdk/pagination.py (cursor-based pagination)

### Slack Connector (US2)

- [X] T082 Write contract test for Slack connector in tests/contract/connectors/test_slack.py (VCR.py cassette)
- [X] T083 Implement SlackConnector in src/connectors/slack/connector.py (channels, threads, users)
- [X] T084 [P] Implement Slack ACL extractor in src/connectors/slack/acl.py (channel membership, private/public)
- [X] T085 [P] Register Slack connector definition in src/connectors/slack/__init__.py

### Jira Connector (US2)

- [X] T086 Write contract test for Jira connector in tests/contract/connectors/test_jira.py (VCR.py cassette)
- [X] T087 Implement JiraConnector in src/connectors/jira/connector.py (issues, comments, projects)
- [X] T088 [P] Implement Jira ACL extractor in src/connectors/jira/acl.py (issue security level, project roles)
- [X] T089 [P] Register Jira connector definition in src/connectors/jira/__init__.py

### Confluence Connector (US2)

- [X] T090 Write contract test for Confluence connector in tests/contract/connectors/test_confluence.py
- [X] T091 Implement ConfluenceConnector in src/connectors/confluence/connector.py (pages, spaces, hierarchy)
- [X] T092 [P] Implement Confluence ACL extractor in src/connectors/confluence/acl.py (space permissions, page restrictions)
- [X] T093 [P] Register Confluence connector definition in src/connectors/confluence/__init__.py

### GitHub Connector (US2)

- [X] T094 Write contract test for GitHub connector in tests/contract/connectors/test_github.py
- [X] T095 Implement GitHubConnector in src/connectors/github/connector.py (repos, issues, PRs, files)
- [X] T096 [P] Implement GitHub ACL extractor in src/connectors/github/acl.py (repo visibility, branch permissions)
- [X] T097 [P] Register GitHub connector definition in src/connectors/github/__init__.py

### Figma Connector (US2)

- [X] T098 Write contract test for Figma connector in tests/contract/connectors/test_figma.py
- [X] T099 Implement FigmaConnector in src/connectors/figma/connector.py (files, comments, versions)
- [X] T100 [P] Implement Figma ACL extractor in src/connectors/figma/acl.py (project permissions, file sharing)
- [X] T101 [P] Register Figma connector definition in src/connectors/figma/__init__.py

### Dropbox Connector (US2)

- [X] T102 Write contract test for Dropbox connector in tests/contract/connectors/test_dropbox.py
- [X] T103 Implement DropboxConnector in src/connectors/dropbox/connector.py (files, folders, shared links)
- [X] T104 [P] Implement Dropbox ACL extractor in src/connectors/dropbox/acl.py (folder permissions, shared links)
- [X] T105 [P] Register Dropbox connector definition in src/connectors/dropbox/__init__.py

### Figma Connector (US2)

- [ ] T098 Write contract test for Figma connector in tests/contract/connectors/test_figma.py
- [ ] T099 Implement FigmaConnector in src/connectors/figma/connector.py (files, comments, versions)
- [ ] T100 [P] Implement Figma ACL extractor in src/connectors/figma/acl.py (file permissions, team access)
- [ ] T101 [P] Register Figma connector definition in src/connectors/figma/__init__.py

### Dropbox Connector (US2)

- [ ] T102 Write contract test for Dropbox connector in tests/contract/connectors/test_dropbox.py
- [ ] T103 Implement DropboxConnector in src/connectors/dropbox/connector.py (files, folders, shared links)
- [ ] T104 [P] Implement Dropbox ACL extractor in src/connectors/dropbox/acl.py (shared folder members, link permissions)
- [ ] T105 [P] Register Dropbox connector definition in src/connectors/dropbox/__init__.py

### Celery Workers (US2)

- [X] T106 Write test for sync task in tests/unit/workers/test_sync_task.py
- [X] T107 Implement sync Celery task in src/workers/sync_task.py (fetch documents, run ingestion pipeline)
- [X] T108 [P] Write test for Celery Beat schedule in tests/unit/workers/test_beat_schedule.py
- [X] T109 [P] Implement Celery Beat scheduler in src/workers/celery_app.py (per-connector cron schedules)
- [X] T110 [P] Implement retry logic with exponential backoff in src/workers/retry_policy.py

### API Endpoints (US2)

- [X] T111 Write test for GET /v1/connectors in tests/integration/api/test_connectors_list.py
- [X] T112 Implement GET /v1/connectors in src/api/routes/connectors.py
- [X] T113 [P] Write test for POST /v1/connectors in tests/integration/api/test_connectors_create.py
- [X] T114 [P] Implement POST /v1/connectors in src/api/routes/connectors.py (validate config, encrypt credentials)
- [X] T115 [P] Write test for PATCH /v1/connectors/{id} in tests/integration/api/test_connectors_update.py
- [X] T116 [P] Implement PATCH /v1/connectors/{id} in src/api/routes/connectors.py
- [X] T117 [P] Write test for DELETE /v1/connectors/{id} in tests/integration/api/test_connectors_delete.py
- [X] T118 [P] Implement DELETE /v1/connectors/{id} in src/api/routes/connectors.py
- [X] T119 Write test for POST /v1/connectors/{id}/sync in tests/integration/api/test_connectors_sync.py
- [X] T120 Implement POST /v1/connectors/{id}/sync in src/api/routes/connectors.py (trigger manual sync)
- [X] T121 [P] Write test for GET /v1/connectors/{id}/sync-runs in tests/integration/api/test_sync_runs.py
- [X] T122 [P] Implement GET /v1/connectors/{id}/sync-runs in src/api/routes/connectors.py
- [X] T123 Create Pydantic schemas in src/api/schemas/connector.py (ConnectorCreate, ConnectorUpdate, SyncRun)

### Integration Tests (US2)

- [X] T124 Write end-to-end test for US2 Scenario 1 in tests/integration/scenarios/test_us2_scenario1.py (add connector, validate, sync)
- [X] T125 Write end-to-end test for US2 Scenario 2 in tests/integration/scenarios/test_us2_scenario2.py (manual sync now)
- [X] T126 Write end-to-end test for US2 Scenario 3 in tests/integration/scenarios/test_us2_scenario3.py (view connector status)
- [X] T127 Write end-to-end test for US2 Scenario 4 in tests/integration/scenarios/test_us2_scenario4.py (rate limit handling)
- [X] T128 Write end-to-end test for US2 Scenario 5 in tests/integration/scenarios/test_us2_scenario5.py (file upload indexing)

---

## Phase 5: User Story 3 - Permission-Aware Retrieval (P1)

**Goal**: Users only see information they have permission to access, respecting source tool permissions

**Independent Test**: Index private Slack channels, query as two users with different access, verify ACL filtering works correctly

**Duration Estimate**: 8-10 hours

### ACL Enforcement (US3)

- [X] T129 Write test for ACL validator in tests/unit/services/test_acl_validator.py (fail-closed for undefined ACLs)
- [X] T130 Implement ACL validator in src/services/acl_validator.py (check user permissions against chunk acl_json)
- [X] T131 [P] Write test for permission check performance in tests/integration/performance/test_acl_performance.py (<100ms)
- [X] T132 Enhance retrieval pipeline in src/retrieval/hybrid_search.py to apply ACL filtering before results
- [X] T133 [P] Write test for identity mapping admin endpoint in tests/integration/api/test_identity_mappings.py
- [X] T134 [P] Implement GET/PATCH /v1/admin/users/{id}/identity-mappings in src/api/routes/admin.py

### Integration Tests (US3)

- [X] T135 Write end-to-end test for US3 Scenario 1 in tests/integration/scenarios/test_us3_scenario1.py (restricted channel filtering)
- [X] T136 Write end-to-end test for US3 Scenario 2 in tests/integration/scenarios/test_us3_scenario2.py (unauthorized document excluded)
- [X] T137 Write end-to-end test for US3 Scenario 3 in tests/integration/scenarios/test_us3_scenario3.py (undefined ACL fail-closed)
- [X] T138 Write end-to-end test for US3 Scenario 4 in tests/integration/scenarios/test_us3_scenario4.py (permission change after sync)

---

## Phase 6: User Story 4 - Slack Bot Interface (P2)

**Goal**: Users interact with ContextDock in Slack via DM, slash commands, or @mentions

**Independent Test**: DM bot with question about indexed content, receive answer with citations in Slack

**Duration Estimate**: 10-12 hours

### Slack Bot Implementation (US4)

- [X] T139 Write test for Slack event handler in tests/unit/integrations/test_slack_bot.py
- [X] T140 Implement Slack bot event listener in src/integrations/slack_bot.py (message events, slash commands, @mentions)
- [X] T141 [P] Write test for Slack message formatter in tests/unit/integrations/test_slack_formatter.py
- [X] T142 [P] Implement Slack message formatter in src/integrations/slack_formatter.py (citations as blocks)
- [X] T143 Write test for ephemeral response logic in tests/unit/integrations/test_slack_privacy.py
- [X] T144 Implement privacy logic in src/integrations/slack_bot.py (suggest DM for public channels)
- [X] T145 Create Slack bot startup script in src/integrations/slack_bot_main.py

### Integration Tests (US4)

- [X] T146 Write end-to-end test for US4 Scenario 1 in tests/integration/scenarios/test_us4_scenario1.py (DM bot, get answer)
- [X] T147 Write end-to-end test for US4 Scenario 2 in tests/integration/scenarios/test_us4_scenario2.py (slash command with ephemeral)
- [X] T148 Write end-to-end test for US4 Scenario 3 in tests/integration/scenarios/test_us4_scenario3.py (@mention, suggest DM)
- [X] T149 Write end-to-end test for US4 Scenario 4 in tests/integration/scenarios/test_us4_scenario4.py (citations with clickable links)

---

## Phase 7: User Story 5 - Create Content with Approval (P3)

**Goal**: Users can request AI to create content in connected tools with mandatory human review and approval

**Independent Test**: Request "create Jira ticket", review preview, approve, verify ticket created in Jira with audit log

**Duration Estimate**: 12-14 hours

### Database Models (US5)

- [ ] T150 Write test for AgentAction model in tests/unit/models/test_agent_action.py
- [ ] T151 Implement AgentAction model in src/models/agent_action.py (type, status, preview_json, expires_at)
- [ ] T152 [P] Write test for AuditLog model in tests/unit/models/test_audit_log.py
- [ ] T153 [P] Implement AuditLog model in src/models/audit_log.py (actor, action, target, details_json)
- [ ] T154 Create Alembic migration: Phase 7 US5 entities (AgentAction, AuditLog - 2 entities)

**Migration Coverage**: All 11 entities covered across 4 migrations: Phase 2 (3), Phase 3 (4), Phase 4 (2), Phase 7 (2)

### Action Handlers (US5)

- [ ] T155 Write test for Jira ticket creation action in tests/unit/agents/test_create_jira_ticket.py
- [ ] T156 Implement CreateJiraTicketAction in src/agents/create_jira_ticket.py (preview generation, execution)
- [ ] T157 [P] Write test for Confluence page creation in tests/unit/agents/test_create_confluence_page.py
- [ ] T158 [P] Implement CreateConfluencePageAction in src/agents/create_confluence_page.py
- [ ] T159 [P] Write test for GitHub issue creation in tests/unit/agents/test_create_github_issue.py
- [ ] T160 [P] Implement CreateGitHubIssueAction in src/agents/create_github_issue.py
- [ ] T161 Write test for preview expiration cleanup in tests/unit/agents/test_action_cleanup.py
- [ ] T162 Implement Celery task for action expiration in src/workers/action_cleanup_task.py (hourly job)

### API Endpoints (US5)

- [ ] T163 Write test for POST /v1/actions in tests/integration/api/test_actions_create.py
- [ ] T164 Implement POST /v1/actions in src/api/routes/actions.py (generate preview, dry-run permission check)
- [ ] T165 [P] Write test for POST /v1/actions/{id}/approve in tests/integration/api/test_actions_approve.py
- [ ] T166 [P] Implement POST /v1/actions/{id}/approve in src/api/routes/actions.py (execute action, create audit log)
- [ ] T167 [P] Write test for GET /v1/actions/{id} in tests/integration/api/test_actions_get.py
- [ ] T168 [P] Implement GET /v1/actions/{id} in src/api/routes/actions.py
- [ ] T169 [P] Write test for DELETE /v1/actions/{id} in tests/integration/api/test_actions_cancel.py
- [ ] T170 [P] Implement DELETE /v1/actions/{id} in src/api/routes/actions.py (cancel action)
- [ ] T171 Create Pydantic schemas in src/api/schemas/action.py (AgentAction, ActionPreview, ActionResult)

### Audit Logging (US5)

- [ ] T172 Write test for audit logger service in tests/unit/services/test_audit_logger.py
- [ ] T173 Implement audit logger in src/services/audit_logger.py (log all write operations)
- [ ] T174 [P] Write test for GET /v1/admin/audit-logs in tests/integration/api/test_audit_logs.py
- [ ] T175 [P] Implement GET /v1/admin/audit-logs in src/api/routes/admin.py (filterable by action, user, date)

### Integration Tests (US5)

- [ ] T176 Write end-to-end test for US5 Scenario 1 in tests/integration/scenarios/test_us5_scenario1.py (generate preview)
- [ ] T177 Write end-to-end test for US5 Scenario 2 in tests/integration/scenarios/test_us5_scenario2.py (edit and approve)
- [ ] T178 Write end-to-end test for US5 Scenario 3 in tests/integration/scenarios/test_us5_scenario3.py (cancel action)
- [ ] T179 Write end-to-end test for US5 Scenario 4 in tests/integration/scenarios/test_us5_scenario4.py (audit log entry)
- [ ] T180 Write end-to-end test for US5 Scenario 5 in tests/integration/scenarios/test_us5_scenario5.py (permission error)

---

## Phase 8: User Story 6 - Web Chat Interface (P2)

**Goal**: Users access ContextDock through a web-based chat interface with rich formatting

**Independent Test**: Open web UI, type question, receive answer with expandable citations and supporting passages

**Duration Estimate**: 8-10 hours

### Web UI Implementation (US6)

- [ ] T181 Write test for static file serving in tests/integration/api/test_static_files.py
- [ ] T182 Create HTML template in src/static/index.html (chat interface with ARIA labels)
- [ ] T183 [P] Create CSS stylesheet in src/static/styles.css (WCAG 2.1 AA contrast, 4.5:1 minimum)
- [ ] T184 [P] Create JavaScript client in src/static/app.js (query submission, citation rendering, keyboard navigation)
- [ ] T185 Configure FastAPI to serve static files in src/main.py (mount /app → src/static/)
- [ ] T186 [P] Write test for accessibility compliance in tests/integration/accessibility/test_wcag.py (axe-core validates FR-048 keyboard nav, FR-049 WCAG 2.1 AA contrast, FR-050 ARIA labels)

### Integration Tests (US6)

- [ ] T187 Write end-to-end test for US6 Scenario 1 in tests/integration/scenarios/test_us6_scenario1.py (type question, get answer)
- [ ] T188 Write end-to-end test for US6 Scenario 2 in tests/integration/scenarios/test_us6_scenario2.py (expand citation)
- [ ] T189 Write end-to-end test for US6 Scenario 3 in tests/integration/scenarios/test_us6_scenario3.py (conversation history)
- [ ] T190 Write end-to-end test for US6 Scenario 4 in tests/integration/scenarios/test_us6_scenario4.py (loading indicator)

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Finalize production-readiness, monitoring, error handling, and documentation

**Duration Estimate**: 10-12 hours

### Error Handling & Graceful Degradation

- [ ] T191 Write test for circuit breaker in tests/unit/integrations/test_circuit_breaker.py
- [ ] T192 Implement circuit breaker for Qdrant in src/integrations/vector_db.py (fallback to keyword-only after 3 failures)
- [ ] T193 [P] Write test for credential expiration handling in tests/unit/workers/test_credential_refresh.py
- [ ] T194 [P] Implement auto-refresh for OAuth tokens in src/workers/sync_task.py (retry with 1min, 5min, 15min backoff)
- [ ] T195 Write test for embedding failure handling in tests/unit/ingestion/test_embedding_failure.py
- [ ] T196 Implement retry with jitter for embedding API in src/ingestion/embeddings.py (1s, 2s, 4s, 8s)

### Monitoring & Observability

- [ ] T197 Write test for structured logging in tests/unit/services/test_logger.py
- [ ] T198 Implement structlog configuration in src/services/logger.py (JSON format, trace IDs)
- [ ] T199 [P] Add Prometheus metrics in src/api/middleware/metrics.py (query latency, sync success rate)
- [ ] T200 [P] Write test for health check details in tests/integration/api/test_health_details.py
- [ ] T201 Enhance /health endpoint with service status checks (database, redis, qdrant connectivity)

### Performance Optimization

- [ ] T202 Write performance test for query latency in tests/integration/performance/test_query_latency.py (p95 <10s)
- [ ] T203 Implement connection pooling for SQLAlchemy in src/config/database.py (pool_size=20, max_overflow=10)
- [ ] T204 [P] Write performance test for concurrent users in tests/integration/performance/test_concurrent_users.py (50 users)
- [ ] T205 [P] Implement caching for identity resolution in src/services/identity_resolution.py (Redis, 1hr TTL)

### Documentation & Deployment

- [ ] T206 Update README.md with architecture overview, setup instructions, contributing guidelines, data privacy policy (FR-039: no customer data used for training models)
- [ ] T207 [P] Create API documentation from OpenAPI spec at /docs endpoint (FastAPI automatic)
- [ ] T208 [P] Create development guide in docs/development.md (running tests, adding connectors)
- [ ] T209 [P] Create deployment guide in docs/deployment.md (Docker Compose quickstart, K8s production, TLS setup via nginx reverse proxy per FR-036, data privacy policy per FR-039: no customer data used for model training)
- [ ] T210 [P] Update docker-compose.yml with all services and resource limits
- [ ] T211 Create Dockerfile with multi-stage build (build, test, production)
- [ ] T212 [P] Create requirements.txt with pinned versions (FastAPI==0.109.0, SQLAlchemy==2.0.25, etc.)
- [ ] T213 [P] Create requirements-dev.txt with dev dependencies (pytest==7.4.3, ruff==0.1.11, mypy==1.8.0)

### Final Validation

- [ ] T214 Run full test suite with coverage report (target 80% minimum, goal 90%)
- [ ] T215 [P] Run ruff check and format across entire codebase
- [ ] T216 [P] Run mypy strict type checking across entire codebase
- [ ] T217 [P] Verify all API endpoints match contracts/api-spec.yaml
- [ ] T218 Run all contract tests with fresh VCR.py cassettes
- [ ] T219 Perform manual smoke test using quickstart.md instructions
- [ ] T220 Update plan.md with actual implementation timeline and learnings

---

## Dependency Graph

**User Story Completion Order** (based on priorities and dependencies):

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational)
    ↓
    ├─→ Phase 3 (US1: Query) ← Must complete first (P1, foundation for all)
    │       ↓
    ├─→ Phase 4 (US2: Connectors) ← Required for data (P1)
    │       ↓
    ├─→ Phase 5 (US3: ACL) ← Security critical (P1)
    │       ↓
    ├─→ Phase 6 (US4: Slack Bot) ← Interface (P2, depends on US1)
    │       ↓
    ├─→ Phase 8 (US6: Web UI) ← Interface (P2, depends on US1)
    │       ↓
    └─→ Phase 7 (US5: Write-back) ← Advanced feature (P3, depends on US2)
            ↓
        Phase 9 (Polish)
```

**Parallelization Opportunities**:

- **Within US1**: Ingestion pipeline (T036-T043) || Retrieval engine (T044-T053) after models complete
- **Within US2**: All 6 connector implementations (T082-T105) can run in parallel after SDK complete
- **Between US4 & US6**: Slack Bot (Phase 6) || Web UI (Phase 8) can run in parallel (both depend on US1)
- **Database migrations**: Can be batched by phase (Phase 2 core, Phase 3 US1, Phase 4 US2, Phase 7 US5)

---

## MVP Scope Recommendation

**Minimum Viable Product** (3-4 weeks for 1-2 developers):
- Phase 1: Setup ✅
- Phase 2: Foundational ✅
- Phase 3: User Story 1 (Query with citations) ✅
- Phase 4: User Story 2 (1-2 connectors only: Slack + Confluence) ⚠️ Reduced
- Phase 5: User Story 3 (ACL filtering) ✅
- Phase 9: Polish (minimal - health checks, basic monitoring) ⚠️ Reduced

**Defer to v2**:
- User Story 4 (Slack Bot) - Can use web UI first
- User Story 5 (Write-back actions) - Read-only is sufficient for MVP
- User Story 6 (Web UI) - CLI or API-only testing acceptable
- Remaining 4 connectors (Jira, GitHub, Figma, Dropbox)

**Rationale**: Core value is **search with citations across connected tools**. US1 (query), US2 (connectors), and US3 (permissions) deliver this. Interfaces (US4, US6) and write-back (US5) are enhancements.

---

## Task Summary

**Total Tasks**: 220
**By Phase**:
- Phase 1 (Setup): 10 tasks
- Phase 2 (Foundational): 16 tasks
- Phase 3 (US1 - Query): 42 tasks
- Phase 4 (US2 - Connectors): 60 tasks
- Phase 5 (US3 - Permissions): 10 tasks
- Phase 6 (US4 - Slack Bot): 11 tasks
- Phase 7 (US5 - Write-back): 32 tasks
- Phase 8 (US6 - Web UI): 10 tasks
- Phase 9 (Polish): 29 tasks

**Test Coverage**: 110 test tasks (50% of total - strict TDD)
**Parallelizable Tasks**: 89 tasks marked [P] (40% can run in parallel)

**Implementation Strategy**: 
1. Complete phases sequentially (Setup → Foundational → US1 → US2 → US3)
2. Within each phase, parallelize tasks marked [P]
3. Run tests continuously (TDD: Red → Green → Refactor)
4. Each user story is independently testable before moving to next
5. Deliver incremental value: After US1+US2+US3, you have a working RAG search platform

**Success Criteria Check**: All 24 success criteria from spec.md can be validated:
- SC-001 to SC-004: Validated by US1 integration tests
- SC-005 to SC-007: Validated by US2 integration tests
- SC-008 to SC-010: Validated by US3 integration tests + performance tests
- SC-011 to SC-013: Validated by Phase 9 health checks and monitoring
- SC-014 to SC-016: Requires production deployment (out of scope for dev)
- SC-017 to SC-019: Validated by US5 integration tests
- SC-020 to SC-021: Validated by Phase 9 performance tests
- SC-022 to SC-024: Validated by US2 connector SDK tests
