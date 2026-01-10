# JIRA Integration Setup Guide

This guide walks you through setting up JIRA Cloud integration with ContextDock.

## Prerequisites

- JIRA Cloud instance (e.g., `yourcompany.atlassian.net`)
- JIRA Admin access (to create API tokens)
- PostgreSQL database running
- Qdrant vector database running

## Step 1: Create JIRA API Token

1. Go to [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **"Create API token"**
3. Give it a label: `ContextDock Integration`
4. Copy the generated token (you won't see it again!)

## Step 2: Configure Environment Variables

Add to your `.env` file:

```bash
# JIRA Configuration
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your_api_token_here

# Optional: Specify projects to sync (comma-separated)
JIRA_PROJECTS=PROJ1,PROJ2,PROJ3

# Optional: JQL filter for selective sync
JIRA_JQL_FILTER=project in (PROJ1, PROJ2) AND status != Closed
```

**Environment Variables:**
- `JIRA_URL`: Your JIRA Cloud instance URL
- `JIRA_EMAIL`: Email of the JIRA user (used for Basic Auth)
- `JIRA_API_TOKEN`: API token created in Step 1
- `JIRA_PROJECTS` (optional): Comma-separated list of project keys to sync
- `JIRA_JQL_FILTER` (optional): Custom JQL query for filtering issues

## Step 3: Create JIRA Connector

Run the setup script:

```bash
python setup_jira.py
```

This will:
1. Create a connector record in the database
2. Store encrypted credentials
3. Validate connection to JIRA

**Manual Setup (Alternative):**

```python
from src.models.connector import Connector
from src.database import SessionLocal

db = SessionLocal()

connector = Connector(
    workspace_id=1,
    connector_type="jira",
    name="JIRA - Your Company",
    config_json={
        "instance_url": "https://yourcompany.atlassian.net",
        "projects": ["PROJ1", "PROJ2"],  # Optional
        "jql_filter": "status != Closed"  # Optional
    },
    credentials_encrypted={
        "email": "your-email@company.com",
        "api_token": "your_api_token"
    },
    is_active=True
)

db.add(connector)
db.commit()
print(f"✅ Connector created with ID: {connector.id}")
```

## Step 4: Run Initial Sync

Sync JIRA issues to ContextDock:

```bash
python sync_jira_issues.py
```

**Expected Output:**
```
🎫 Starting JIRA sync...
📊 Connector: JIRA - Your Company (ID: 2)
🔄 Syncing issues from projects: PROJ1, PROJ2
✅ Synced issue PROJ1-123: Implement user authentication
✅ Synced issue PROJ1-124: Fix login bug
...
🎉 Sync complete! Synced 245 issues
⏱️  Duration: 3m 24s
```

## Step 5: Verify Sync

Check synced issues:

```python
from src.models.document import Document
from src.database import SessionLocal

db = SessionLocal()

# Count JIRA issues
jira_count = db.query(Document).filter(
    Document.source_type == "jira"
).count()

print(f"📊 Total JIRA issues synced: {jira_count}")

# Sample issues
sample_issues = db.query(Document).filter(
    Document.source_type == "jira"
).limit(5).all()

for doc in sample_issues:
    print(f"  🎫 {doc.title} - {doc.url}")
```

## Data Synced

ContextDock syncs the following from JIRA:

### Issue Fields:
- **Summary** (title)
- **Description** (full text content)
- **Issue Key** (e.g., PROJ-123)
- **Status** (Open, In Progress, Done, etc.)
- **Issue Type** (Story, Bug, Task, etc.)
- **Priority** (Highest, High, Medium, Low, Lowest)
- **Assignee** (user assigned to the issue)
- **Reporter** (user who created the issue)
- **Labels** (tags on the issue)
- **Created Date**
- **Updated Date**

### Comments:
- All comments on each issue
- Comment author and timestamp
- Comment body text

### Metadata:
- Project information (name, key)
- Issue URL (direct link to JIRA)

## Access Control (ACL)

JIRA issues include ACL information:

```json
{
  "connector_type": "jira",
  "project_key": "PROJ1",
  "project_name": "Project Alpha",
  "issue_type": "Story",
  "allowed_account_ids": ["jira:123abc", "jira:456def"]
}
```

**ACL Rules:**
- Users must have access to the project
- Restricted issues (with specific visibility) are filtered
- Comments inherit parent issue permissions

## Incremental Sync

Run sync regularly to fetch new/updated issues:

```bash
# Manual sync
python sync_jira_issues.py

# With date filter (only recent updates)
python sync_jira_issues.py --since "2026-01-01"
```

**Using Celery (Scheduled):**

```python
# In celery beat schedule
from celery.schedules import crontab

app.conf.beat_schedule = {
    'sync-jira-hourly': {
        'task': 'src.workers.sync_task.sync_connector',
        'schedule': crontab(minute=0),  # Every hour
        'args': (2,)  # Connector ID
    }
}
```

## JQL Query Examples

Customize sync with JQL filters:

```bash
# Only open issues
JIRA_JQL_FILTER="status in (Open, 'In Progress')"

# Issues updated in last 7 days
JIRA_JQL_FILTER="updated >= -7d"

# Specific issue types
JIRA_JQL_FILTER="issuetype in (Bug, Story)"

# Issues assigned to you
JIRA_JQL_FILTER="assignee = currentUser()"

# Complex filter
JIRA_JQL_FILTER="project = PROJ AND status != Closed AND priority in (High, Highest)"
```

## Troubleshooting

### Authentication Failed

**Error:** `401 Unauthorized`

**Solutions:**
- Verify API token is correct
- Check email matches JIRA user
- Ensure API token hasn't expired
- Verify user has project access

### Rate Limit Errors

**Error:** `429 Too Many Requests`

**Solutions:**
- Reduce sync frequency
- JIRA Cloud limit: 10 requests/second
- Script automatically handles rate limiting
- Consider syncing specific projects only

### Empty Results

**Problem:** No issues synced

**Check:**
- Verify project keys are correct
- Check JQL filter syntax
- Ensure user has view permission
- Try syncing without JQL filter first

### Missing Comments

**Problem:** Comments not appearing

**Solutions:**
- Check user has comment view permission
- Verify `read:jira-work` scope is granted
- Comments may be restricted by project settings

## Advanced Configuration

### Custom Field Mapping

Edit `src/connectors/jira/connector.py` to include custom fields:

```python
fields = [
    "summary",
    "description",
    "status",
    "customfield_10001",  # Your custom field
]
```

### Webhook Support (Future)

For real-time sync, configure JIRA webhooks:

1. Go to JIRA Settings → System → Webhooks
2. Create webhook pointing to: `https://your-domain.com/webhooks/jira`
3. Select events: Issue Created, Updated, Deleted

## Next Steps

- ✅ JIRA issues synced and indexed
- ✅ Search JIRA content via Slack bot
- 📝 Set up scheduled sync (Celery)
- 🔔 Configure webhooks for real-time updates
- 🎯 Add more project filters

## API Documentation

- [JIRA Cloud REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [JQL Reference](https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
- [API Tokens](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/)
