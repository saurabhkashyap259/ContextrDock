# Data Model: ContextDock RAG Platform MVP

**Date**: 2026-01-06  
**Purpose**: Define database schema, entity relationships, and validation rules

## Overview

The data model supports workspace isolation, connector configuration, document indexing with ACL metadata, conversation history, write-back actions with approval workflow, and comprehensive audit logging.

## Database Schema

### Workspace

Logical container for a team's data, supporting future multi-tenancy.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique workspace identifier |
| name | VARCHAR(255) | NOT NULL | Workspace display name |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation timestamp |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last update timestamp |

**Indexes**:
- Primary key on `id`

**Relationships**:
- One-to-many with User, Connector, Document, Conversation, AgentAction, AuditLog

---

### User

Individual with email-based identity and per-connector mappings.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique user identifier |
| workspace_id | UUID | FK(Workspace.id), NOT NULL | Workspace association |
| email | VARCHAR(255) | NOT NULL, UNIQUE(workspace_id, email) | Primary email (normalized lowercase) |
| name | VARCHAR(255) | NOT NULL | Display name |
| role | ENUM('admin', 'member') | NOT NULL, DEFAULT 'member' | Authorization role |
| connector_identities | JSONB | DEFAULT '{}' | Per-connector identity mappings: `{"slack": "U123", "jira": "account-id"}` |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation timestamp |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last update timestamp |

**Indexes**:
- Primary key on `id`
- Unique index on `(workspace_id, email)`
- Index on `workspace_id` for workspace queries

**Validation Rules**:
- Email must be valid format and lowercase
- connector_identities keys must match registered connector types
- Role must be one of defined enum values

**Relationships**:
- Many-to-one with Workspace
- One-to-many with Conversation, AgentAction, AuditLog

---

### ConnectorDefinition

Metadata describing available connector types (read from code, not user-created).

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| type | VARCHAR(50) | PK | Connector type identifier (slack, jira, etc.) |
| name | VARCHAR(255) | NOT NULL | Human-readable name |
| version | VARCHAR(20) | NOT NULL | Connector version (semantic versioning) |
| capabilities | JSONB | NOT NULL | Supported capabilities: `{"read": true, "write": false}` |
| config_schema | JSONB | NOT NULL | JSON schema for configuration fields |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Registration timestamp |

**Indexes**:
- Primary key on `type`

**Validation Rules**:
- Type must match registered SDK connector class
- Version must follow semver format
- config_schema must be valid JSON Schema

---

### Connector

User-configured data source instance.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique connector identifier |
| workspace_id | UUID | FK(Workspace.id), NOT NULL | Workspace association |
| type | VARCHAR(50) | FK(ConnectorDefinition.type), NOT NULL | Connector type |
| name | VARCHAR(255) | NOT NULL | User-assigned name |
| config_json | JSONB | NOT NULL | Connector configuration (scopes, settings) |
| credentials_encrypted | BYTEA | NOT NULL | Encrypted OAuth tokens/API keys |
| status | ENUM('active', 'error', 'disabled') | NOT NULL, DEFAULT 'active' | Connector status |
| sync_schedule | VARCHAR(20) | NOT NULL | Schedule: 'hourly', '6hours', 'daily' |
| last_sync_at | TIMESTAMP | NULL | Last successful sync completion time |
| last_error | TEXT | NULL | Last error message if status='error' |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation timestamp |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last update timestamp |

**Indexes**:
- Primary key on `id`
- Index on `workspace_id` for workspace queries
- Index on `type` for connector type queries
- Index on `status` for health monitoring

**Validation Rules**:
- config_json must validate against ConnectorDefinition.config_schema
- credentials_encrypted must be Fernet-encrypted
- sync_schedule must be one of allowed values
- Name must be unique within workspace

**Relationships**:
- Many-to-one with Workspace, ConnectorDefinition
- One-to-many with SyncRun, Document

---

### SyncRun

Record of a connector sync operation.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique sync run identifier |
| connector_id | UUID | FK(Connector.id), NOT NULL | Associated connector |
| started_at | TIMESTAMP | NOT NULL | Sync start time |
| ended_at | TIMESTAMP | NULL | Sync completion time (NULL if running) |
| status | ENUM('running', 'success', 'partial', 'failed') | NOT NULL | Sync status |
| documents_added | INTEGER | DEFAULT 0 | Count of new documents |
| documents_updated | INTEGER | DEFAULT 0 | Count of updated documents |
| documents_deleted | INTEGER | DEFAULT 0 | Count of deleted documents |
| error_summary | TEXT | NULL | Error details if status='failed' |
| cursor_state_json | JSONB | DEFAULT '{}' | Incremental sync cursor state |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation timestamp |

**Indexes**:
- Primary key on `id`
- Index on `connector_id` for connector history
- Index on `started_at DESC` for recent sync queries

**Validation Rules**:
- ended_at must be >= started_at if not NULL
- Status 'success' requires ended_at NOT NULL
- cursor_state_json format depends on connector type

**Relationships**:
- Many-to-one with Connector

---

### Document

Normalized representation of source content with metadata.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique document identifier |
| workspace_id | UUID | FK(Workspace.id), NOT NULL | Workspace association |
| connector_id | UUID | FK(Connector.id), NOT NULL | Source connector |
| source_type | VARCHAR(50) | NOT NULL | Content type (slack_message, jira_issue, etc.) |
| source_id | VARCHAR(500) | NOT NULL | External ID from source system |
| title | VARCHAR(1000) | NOT NULL | Document title |
| url | VARCHAR(2000) | NOT NULL | Deep link to original content |
| content_hash | VARCHAR(64) | NOT NULL | SHA256 hash of content for change detection |
| indexed_at | TIMESTAMP | NOT NULL | When document was last indexed |
| updated_at_source | TIMESTAMP | NOT NULL | Last update time in source system |
| metadata_json | JSONB | DEFAULT '{}' | Additional metadata (author, tags, etc.) |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation timestamp |

**Indexes**:
- Primary key on `id`
- Unique index on `(connector_id, source_id)` for deduplication
- Index on `workspace_id` for workspace queries
- Index on `content_hash` for change detection
- Index on `updated_at_source DESC` for freshness queries

**Validation Rules**:
- URL must be valid HTTP/HTTPS format
- content_hash must be 64-character hex string (SHA256)
- source_id must be unique within connector

**Relationships**:
- Many-to-one with Workspace, Connector
- One-to-many with DocumentChunk

---

### DocumentChunk

Searchable segment of a document with ACL metadata.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique chunk identifier |
| document_id | UUID | FK(Document.id), NOT NULL, ON DELETE CASCADE | Parent document |
| chunk_index | INTEGER | NOT NULL | Sequential chunk number (0-based) |
| content | TEXT | NOT NULL | Chunk text content (500-1000 tokens) |
| token_count | INTEGER | NOT NULL | Exact token count for this chunk |
| embedding_id | VARCHAR(100) | NOT NULL | Vector DB reference (Qdrant point ID) |
| acl_json | JSONB | NOT NULL | ACL metadata: `{"allowed_user_ids": [], "allowed_channel_ids": [], "visibility": "private"}` |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation timestamp |

**Indexes**:
- Primary key on `id`
- Unique index on `(document_id, chunk_index)` for ordering
- Index on `document_id` for document retrieval
- Index on `embedding_id` for vector DB correlation

**Validation Rules**:
- chunk_index must be >= 0 and sequential within document
- content must not be empty
- token_count must match actual tiktoken count
- acl_json must have required fields (allowed_user_ids, visibility)

**Relationships**:
- Many-to-one with Document

**State Transitions**:
- Created → (document deleted) → Deleted (cascade)
- Created → (document updated, content changed) → Recreated with new embedding

---

### Conversation

Multi-turn dialog between user and assistant.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique conversation identifier |
| workspace_id | UUID | FK(Workspace.id), NOT NULL | Workspace association |
| user_id | UUID | FK(User.id), NOT NULL | Conversation owner |
| channel_type | ENUM('web', 'slack_dm', 'slack_channel') | NOT NULL | Interface type |
| external_channel_id | VARCHAR(255) | NULL | Slack channel ID if channel_type='slack_channel' |
| title | VARCHAR(500) | NULL | Optional conversation title |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation timestamp |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last message timestamp |

**Indexes**:
- Primary key on `id`
- Index on `(workspace_id, user_id)` for user conversations
- Index on `updated_at DESC` for recent conversations
- Index on `(channel_type, external_channel_id)` for Slack channel correlation

**Validation Rules**:
- external_channel_id required if channel_type='slack_channel'
- external_channel_id must be NULL if channel_type='web' or 'slack_dm'

**Relationships**:
- Many-to-one with Workspace, User
- One-to-many with Message

---

### Message

Individual exchange in a conversation.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique message identifier |
| conversation_id | UUID | FK(Conversation.id), NOT NULL, ON DELETE CASCADE | Parent conversation |
| role | ENUM('user', 'assistant') | NOT NULL | Message sender |
| content | TEXT | NOT NULL | Message text |
| citations_json | JSONB | NULL | Citations if role='assistant': `[{"document_id": "...", "chunk_ids": [...], "title": "...", "url": "..."}]` |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation timestamp |

**Indexes**:
- Primary key on `id`
- Index on `(conversation_id, created_at ASC)` for message ordering
- Index on `created_at DESC` for recent messages

**Validation Rules**:
- Content must not be empty
- citations_json only valid if role='assistant'
- Each citation must have valid document_id reference

**Relationships**:
- Many-to-one with Conversation

---

### AgentAction

Proposed or executed write operation with approval workflow.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique action identifier |
| workspace_id | UUID | FK(Workspace.id), NOT NULL | Workspace association |
| user_id | UUID | FK(User.id), NOT NULL | Requesting user |
| conversation_id | UUID | FK(Conversation.id), NULL | Originating conversation |
| type | VARCHAR(100) | NOT NULL | Action type (create_jira_ticket, create_confluence_page, etc.) |
| status | ENUM('draft', 'approved', 'executing', 'executed', 'failed', 'cancelled') | NOT NULL, DEFAULT 'draft' | Action status |
| preview_json | JSONB | NOT NULL | Structured preview: `{"title": "...", "description": "...", "project": "..."}` |
| execution_result_json | JSONB | NULL | Result after execution: `{"created_url": "...", "external_id": "..."}` |
| error_message | TEXT | NULL | Error details if status='failed' |
| expires_at | TIMESTAMP | NOT NULL | Preview expiration time (1 hour from creation) |
| approved_at | TIMESTAMP | NULL | User approval timestamp |
| executed_at | TIMESTAMP | NULL | Execution completion timestamp |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Creation timestamp |

**Indexes**:
- Primary key on `id`
- Index on `(workspace_id, user_id)` for user actions
- Index on `status` for pending actions queue
- Index on `expires_at` for cleanup of stale drafts
- Index on `created_at DESC` for recent actions

**Validation Rules**:
- preview_json schema must match action type schema
- approved_at required if status IN ('executing', 'executed')
- executed_at required if status='executed'
- error_message required if status='failed'
- expires_at must be > created_at

**Relationships**:
- Many-to-one with Workspace, User
- Many-to-one (optional) with Conversation

**State Transitions**:
- draft → approved → executing → executed (happy path)
- draft → cancelled (user cancellation)
- executing → failed (execution error)
- draft → expired (automatic cleanup after expires_at)

---

### AuditLog

Immutable record of significant actions for compliance and debugging.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK | Unique log entry identifier |
| workspace_id | UUID | FK(Workspace.id), NOT NULL | Workspace association |
| actor_user_id | UUID | FK(User.id), NULL | User who performed action (NULL for system) |
| action | VARCHAR(100) | NOT NULL | Action type (connector.created, action.approved, etc.) |
| target_type | VARCHAR(50) | NOT NULL | Target entity type (Connector, AgentAction, etc.) |
| target_id | UUID | NOT NULL | Target entity ID |
| details_json | JSONB | DEFAULT '{}' | Additional details: `{"before": {...}, "after": {...}}` |
| ip_address | INET | NULL | Client IP address if applicable |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | Event timestamp |

**Indexes**:
- Primary key on `id`
- Index on `workspace_id` for workspace audit queries
- Index on `actor_user_id` for user activity queries
- Index on `(target_type, target_id)` for entity history
- Index on `created_at DESC` for recent events
- Index on `action` for action type filtering

**Validation Rules**:
- action must follow naming convention: `<entity>.<verb>` (e.g., connector.created)
- target_type must match existing entity type
- created_at is immutable (INSERT only, no UPDATE/DELETE)

**Relationships**:
- Many-to-one with Workspace
- Many-to-one (optional) with User

**Retention Policy**:
- Keep all logs for 1 year minimum (compliance requirement)
- Archive logs >1 year to cold storage
- Never delete logs for executed write actions (permanent audit trail)

---

## Entity Relationships Diagram

```
Workspace (1) ─────┬─── (N) User
                   ├─── (N) Connector ───┬─── (N) SyncRun
                   │                     └─── (N) Document ─── (N) DocumentChunk
                   ├─── (N) Conversation ─── (N) Message
                   ├─── (N) AgentAction
                   └─── (N) AuditLog

ConnectorDefinition (1) ─── (N) Connector

User (1) ─────┬─── (N) Conversation
              ├─── (N) AgentAction
              └─── (N) AuditLog

Conversation (1) ─── (N) AgentAction (optional)
```

## Data Integrity Constraints

1. **Cascade Deletes**:
   - Document deleted → all DocumentChunks deleted + vector DB cleanup
   - Conversation deleted → all Messages deleted
   - Workspace deleted → all related entities deleted (soft delete with retention)

2. **Foreign Key Checks**:
   - All FK constraints enforced at database level
   - ON DELETE RESTRICT for User (prevent deletion if audit logs exist)
   - ON DELETE CASCADE for dependent entities (Chunks, Messages)

3. **Unique Constraints**:
   - (workspace_id, email) for User - prevent duplicate emails per workspace
   - (connector_id, source_id) for Document - prevent duplicate source documents
   - (document_id, chunk_index) for DocumentChunk - ensure chunk ordering

4. **Check Constraints**:
   - chunk_index >= 0
   - token_count > 0
   - ended_at >= started_at (SyncRun)
   - expires_at > created_at (AgentAction)

## Validation Rules Summary

| Entity | Key Validations |
|--------|----------------|
| User | Email format, lowercase normalization, valid role enum |
| Connector | Config matches schema, encrypted credentials, valid schedule |
| Document | Valid URL, SHA256 content hash, unique source_id per connector |
| DocumentChunk | Sequential chunk_index, non-empty content, valid ACL JSON |
| AgentAction | Valid state transitions, preview schema validation, expiration check |
| AuditLog | Immutable (INSERT only), valid action naming convention |

## Migration Strategy

1. **Phase 0**: Core entities (Workspace, User, ConnectorDefinition)
2. **Phase 1**: Connector infrastructure (Connector, SyncRun)
3. **Phase 2**: Document storage (Document, DocumentChunk)
4. **Phase 3**: Conversation (Conversation, Message)
5. **Phase 4**: Write-back (AgentAction)
6. **Phase 5**: Audit (AuditLog)

Each migration includes:
- Schema creation
- Indexes
- Foreign keys
- Sample data for testing

## Performance Considerations

- **Partitioning**: Consider partitioning AuditLog by created_at (monthly) if volume >10M rows
- **Archival**: Move DocumentChunks for deleted Documents to archive table
- **Read Replicas**: Use read replicas for analytics queries on AuditLog
- **Connection Pooling**: Configure SQLAlchemy pool (min=5, max=20 connections)
- **Batch Operations**: Use bulk inserts for DocumentChunks (100-500 per transaction)

## Security Notes

- **Encryption at Rest**: credentials_encrypted uses Fernet (symmetric), key in environment
- **PII Handling**: User.email is PII, respect GDPR/CCPA deletion requests
- **ACL Enforcement**: Always check acl_json before returning chunks in query results
- **Audit Trail**: All mutations to Connector, AgentAction must generate AuditLog entries
