# Quickstart Guide: ContextDock RAG Platform MVP

**Date**: 2026-01-06  
**Purpose**: Step-by-step guide for setting up, testing, and integrating with ContextDock

## Prerequisites

- Python 3.11+ installed
- Docker and Docker Compose installed
- Git for version control
- API keys for:
  - OpenAI (for embeddings and LLM)
  - At least one connector service (Slack, Jira, Confluence, or GitHub)

## 1. Local Setup (5 minutes)

### Clone and Setup Environment

```bash
# Clone repository
git clone https://github.com/contextdock/contextdock.git
cd contextdock

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy environment template
cp .env.example .env
```

### Configure Environment Variables

Edit `.env` file:

```bash
# Database
DATABASE_URL=postgresql://contextdock:password@localhost:5432/contextdock
REDIS_URL=redis://localhost:6379/0

# Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=  # Optional for local dev

# LLM Provider
OPENAI_API_KEY=your-openai-api-key-here
EMBEDDING_MODEL=text-embedding-3-small  # Default

# Encryption (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
FERNET_KEY=your-generated-fernet-key-here

# JWT Authentication
JWT_SECRET_KEY=your-random-secret-key-here  # Generate with: openssl rand -hex 32
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Application
LOG_LEVEL=INFO
```

### Start Infrastructure Services

```bash
# Start PostgreSQL, Redis, and Qdrant
docker-compose up -d postgres redis qdrant

# Wait for services to be ready
docker-compose ps
```

### Initialize Database

```bash
# Run migrations
alembic upgrade head

# Create initial workspace and admin user
python scripts/init_workspace.py \
  --workspace-name "My Company" \
  --admin-email "admin@example.com" \
  --admin-name "Admin User"

# Script outputs:
# ✓ Created workspace: My Company (workspace_id: ...)
# ✓ Created admin user: admin@example.com
# ✓ Generated admin JWT token: eyJ...
```

## 2. Run the Application (2 minutes)

### Start API Server

```bash
# Terminal 1: Start FastAPI server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Test health endpoint
curl http://localhost:8000/health
# Expected: {"status": "healthy", "version": "1.0.0", "timestamp": "..."}
```

### Start Background Workers

```bash
# Terminal 2: Start Celery worker for sync jobs
celery -A src.workers.celery_app worker --loglevel=info

# Terminal 3: Start Celery beat for scheduled syncs
celery -A src.workers.celery_app beat --loglevel=info
```

## 3. Connect First Data Source (10 minutes)

### Example: Connect Confluence

#### Step 1: Get Confluence API Token

1. Log into Confluence
2. Go to: Profile → Settings → Password → Create API Token
3. Copy the generated token

#### Step 2: Create Connector via API

```bash
# Set admin token from init script output
export TOKEN="eyJ..."

# Create Confluence connector
curl -X POST http://localhost:8000/v1/connectors \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "confluence",
    "name": "Company Confluence",
    "config": {
      "base_url": "https://your-domain.atlassian.net/wiki",
      "spaces": ["ENG", "PRODUCT"],
      "include_attachments": false
    },
    "credentials": {
      "email": "your-email@example.com",
      "api_token": "your-confluence-api-token"
    },
    "sync_schedule": "6hours"
  }'

# Response includes connector_id
# Save connector_id for next steps
export CONNECTOR_ID="returned-uuid"
```

#### Step 3: Trigger Manual Sync

```bash
# Start first sync
curl -X POST http://localhost:8000/v1/connectors/$CONNECTOR_ID/sync \
  -H "Authorization: Bearer $TOKEN"

# Response: {"sync_run_id": "...", "status": "queued"}
export SYNC_RUN_ID="returned-uuid"

# Monitor sync progress (check Celery worker logs or query status)
curl http://localhost:8000/v1/connectors/$CONNECTOR_ID/sync-runs \
  -H "Authorization: Bearer $TOKEN"

# Expected output shows sync progress:
# {
#   "sync_runs": [{
#     "id": "...",
#     "status": "running",  # or "success" when complete
#     "documents_added": 150,
#     "documents_updated": 0,
#     "started_at": "...",
#     "ended_at": null
#   }]
# }
```

## 4. Test Query Endpoint (3 minutes)

### Ask First Question

```bash
# Query the indexed content
curl -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the main features of our product?"
  }'

# Expected response:
# {
#   "answer": "Based on the available documentation, the main features include...",
#   "citations": [
#     {
#       "document_id": "...",
#       "title": "Product Overview",
#       "url": "https://your-domain.atlassian.net/wiki/spaces/PRODUCT/pages/12345",
#       "source_type": "confluence_page",
#       "last_indexed": "2026-01-06T10:30:00Z"
#     }
#   ],
#   "conversation_id": "...",
#   "metadata": {
#     "sources_searched": 150,
#     "retrieval_time_ms": 120,
#     "generation_time_ms": 1800
#   }
# }
```

### Follow-up Question (Using Conversation)

```bash
# Use conversation_id from previous response
export CONVERSATION_ID="returned-uuid"

curl -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can you elaborate on the authentication feature?",
    "conversation_id": "'$CONVERSATION_ID'"
  }'
```

## 5. Test Write-back Action (5 minutes)

### Create Jira Connector First

```bash
# Similar to Confluence example
curl -X POST http://localhost:8000/v1/connectors \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "jira",
    "name": "Company Jira",
    "config": {
      "base_url": "https://your-domain.atlassian.net",
      "projects": ["ENG", "BUGS"]
    },
    "credentials": {
      "email": "your-email@example.com",
      "api_token": "your-jira-api-token"
    },
    "sync_schedule": "6hours"
  }'

export JIRA_CONNECTOR_ID="returned-uuid"
```

### Create Action Preview

```bash
# Request to create a Jira ticket (preview only)
curl -X POST http://localhost:8000/v1/actions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "create_jira_ticket",
    "context": {
      "summary": "API timeout issue in production",
      "description": "Users are experiencing timeouts when calling /v1/query endpoint",
      "project": "BUGS",
      "issue_type": "Bug",
      "priority": "High"
    }
  }'

# Response shows preview with editable fields:
# {
#   "id": "action-uuid",
#   "type": "create_jira_ticket",
#   "status": "draft",
#   "preview": {
#     "summary": "API timeout issue in production",
#     "description": "Users are experiencing timeouts...",
#     "project": "BUGS",
#     "issue_type": "Bug",
#     "priority": "High",
#     "labels": []
#   },
#   "expires_at": "2026-01-06T11:30:00Z",  # 1 hour expiry
#   "created_at": "2026-01-06T10:30:00Z"
# }

export ACTION_ID="returned-uuid"
```

### Review and Approve Action

```bash
# Option 1: Approve as-is
curl -X POST http://localhost:8000/v1/actions/$ACTION_ID/approve \
  -H "Authorization: Bearer $TOKEN"

# Option 2: Edit preview before approval
curl -X POST http://localhost:8000/v1/actions/$ACTION_ID/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "edited_preview": {
      "summary": "API timeout issue in production (URGENT)",
      "labels": ["production", "urgent"]
    }
  }'

# Response after execution:
# {
#   "id": "action-uuid",
#   "status": "executed",
#   "execution_result": {
#     "created_url": "https://your-domain.atlassian.net/browse/BUGS-123",
#     "external_id": "BUGS-123"
#   },
#   "executed_at": "2026-01-06T10:31:00Z"
# }
```

## 6. Test Permission-Aware Retrieval (5 minutes)

### Create Second User with Limited Access

```bash
# Create member user
curl -X POST http://localhost:8000/v1/admin/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "member@example.com",
    "name": "Member User",
    "role": "member"
  }'

# Response includes user_id and JWT token for member
export MEMBER_TOKEN="returned-member-token"
```

### Configure Identity Mapping

```bash
# Map member to Slack user with limited channel access
curl -X PATCH http://localhost:8000/v1/admin/users/{member_user_id}/identity-mappings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "connector_identities": {
      "slack": "U9876XYZ",  # Slack user with access to #general only
      "confluence": "account-id-member"
    }
  }'
```

### Test ACL Filtering

```bash
# Admin query (has access to all channels)
curl -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was discussed in the leadership meeting?"
  }'
# Expected: Returns content from #leadership channel

# Member query (no access to #leadership)
curl -X POST http://localhost:8000/v1/query \
  -H "Authorization: Bearer $MEMBER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was discussed in the leadership meeting?"
  }'
# Expected: "not enough evidence" response (filtered out #leadership content)
```

## 7. Integration Scenarios

### Scenario 1: Slack Bot Integration

```bash
# Install Slack app and get bot token
# Configure Slack credentials in admin console

# Start Slack bot listener
python -m src.integrations.slack_bot

# Test in Slack:
# 1. DM the bot: "What is our onboarding process?"
# 2. Use slash command: /contextdock What repos should I clone?
# 3. @mention in channel: @ContextDock where is the API documentation?
```

### Scenario 2: Web UI (Simple HTML Demo)

```bash
# Serve simple web UI from FastAPI static files
# Open browser to: http://localhost:8000/app

# UI provides:
# - Chat interface for asking questions
# - Citation links to source documents
# - Expandable supporting passages
# - Conversation history
```

### Scenario 3: Automated Sync Monitoring

```bash
# Query sync status for all connectors
curl http://localhost:8000/v1/connectors \
  -H "Authorization: Bearer $TOKEN"

# Check for failed syncs
curl http://localhost:8000/v1/admin/audit-logs?action=sync.failed \
  -H "Authorization: Bearer $TOKEN"

# View connector health dashboard
# Access Grafana at: http://localhost:3000 (if configured)
```

## 8. Running Tests

### Unit Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### Integration Tests

```bash
# Start test database
docker-compose -f docker-compose.test.yml up -d

# Run integration tests
pytest tests/integration/ -v

# Cleanup
docker-compose -f docker-compose.test.yml down -v
```

### Contract Tests (Against Real APIs)

```bash
# Set connector credentials in test environment
export SLACK_TEST_TOKEN="xoxb-test-token"
export JIRA_TEST_TOKEN="test-api-token"

# Run contract tests (uses VCR.py cassettes)
pytest tests/contract/ -v

# Update cassettes (re-record API responses)
pytest tests/contract/ -v --record-mode=rewrite
```

## 9. Troubleshooting

### Common Issues

**Issue**: Sync fails with "Rate limit exceeded"

```bash
# Check connector configuration
curl http://localhost:8000/v1/connectors/$CONNECTOR_ID \
  -H "Authorization: Bearer $TOKEN"

# Adjust sync schedule to reduce frequency
curl -X PATCH http://localhost:8000/v1/connectors/$CONNECTOR_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sync_schedule": "daily"}'
```

**Issue**: Query returns "not enough evidence" despite indexed content

```bash
# Check if user has identity mapping for connector
curl http://localhost:8000/v1/admin/users/{user_id}/identity-mappings \
  -H "Authorization: Bearer $TOKEN"

# Verify ACL metadata was captured during sync
# Check PostgreSQL: SELECT acl_json FROM document_chunks LIMIT 5;
```

**Issue**: Embeddings not generating

```bash
# Verify OpenAI API key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Check embedding service health in logs
tail -f logs/app.log | grep "embedding"

# Test embedding generation directly
python -c "
from src.ingestion.embeddings import generate_embedding
result = generate_embedding('test text')
print(f'Generated embedding with {len(result)} dimensions')
"
```

## 10. Next Steps

- **Add More Connectors**: Follow connector setup pattern for Slack, GitHub, Figma, Dropbox
- **Configure Slack Bot**: Enable interactive Slack experience
- **Setup Monitoring**: Configure Prometheus + Grafana dashboards
- **Production Deployment**: Use Kubernetes manifests in `k8s/` directory
- **Customize Chunking**: Adjust chunk size and overlap in `src/ingestion/chunker.py`
- **Fine-tune Retrieval**: Experiment with hybrid search weights in `src/retrieval/search.py`

## Resources

- **API Documentation**: http://localhost:8000/docs (OpenAPI UI)
- **Admin Console**: http://localhost:8000/admin
- **Logs**: `logs/app.log`, `logs/celery.log`
- **Metrics**: http://localhost:9090 (Prometheus, if configured)
- **Vector DB UI**: http://localhost:6333/dashboard (Qdrant)

## Support

- **Issues**: https://github.com/contextdock/contextdock/issues
- **Documentation**: https://docs.contextdock.io
- **Community**: https://discord.gg/contextdock
