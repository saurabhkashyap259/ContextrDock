# JIRA Quick Start

Get JIRA integration running in 5 minutes.

## 1. Get JIRA API Token

Visit: https://id.atlassian.com/manage-profile/security/api-tokens

- Click "Create API token"
- Name: `ContextDock`
- **Copy the token** (you won't see it again)

## 2. Configure .env

Add these lines to `.env`:

```bash
# JIRA Configuration
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=paste_your_token_here
```

## 3. Setup Connector

```bash
python setup_jira.py
```

Expected output:
```
🎫 Setting up JIRA connector...
   URL: https://yourcompany.atlassian.net
   Email: your-email@company.com
✅ Created JIRA connector (ID: 2)
```

## 4. Sync Issues

```bash
python sync_jira_issues.py
```

This will:
- Fetch all issues from your JIRA instance
- Generate embeddings for each issue
- Index in Qdrant for search

Expected output:
```
🎫 Starting JIRA sync...
📊 Connector: JIRA - yourcompany.atlassian.net (ID: 2)
✅ Synced issue PROJ-123: User authentication
✅ Synced issue PROJ-124: Fix login bug
...
🎉 Sync complete! Synced 245 issues
```

## 5. Test Search

Ask the Slack bot:

```
@ContextDock What JIRA issues are open for the login feature?
```

or

```
/ask Show me high priority bugs in JIRA
```

## Optional: Selective Sync

### Sync Specific Projects

```bash
# In .env
JIRA_PROJECTS=PROJ1,PROJ2,ENG
```

### Filter by Status

```bash
# In .env
JIRA_JQL_FILTER=status in (Open, 'In Progress', 'To Do')
```

### Filter by Date

```bash
# In .env
JIRA_JQL_FILTER=updated >= -30d
```

### Complex Filters

```bash
# In .env
JIRA_JQL_FILTER=project = PROJ AND priority in (High, Highest) AND status != Closed
```

## Common Issues

**401 Unauthorized:**
- Check email and API token are correct
- Verify token hasn't been revoked

**Empty Results:**
- Check project keys in JIRA_PROJECTS
- Verify JQL filter syntax
- Try without filters first

**Rate Limit:**
- Script automatically handles rate limits
- JIRA Cloud: 10 requests/second

## Next Steps

- ✅ Issues synced and searchable
- 📅 Set up scheduled sync (hourly/daily)
- 🔔 Configure webhooks for real-time updates
- 🎯 Customize JQL filters

## Full Documentation

See [JIRA_SETUP.md](docs/JIRA_SETUP.md) for complete guide.
