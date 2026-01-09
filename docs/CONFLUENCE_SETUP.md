# Confluence Connector Setup Guide

This guide helps you connect ContextDock to your Confluence Cloud instance to index pages, spaces, and enable intelligent search.

## Overview

The Confluence connector:
- ✅ Fetches pages and blog posts from Confluence Cloud
- ✅ Indexes page content with hierarchy and metadata
- ✅ Supports space-level and page-level permissions (ACL)
- ✅ Enables incremental sync (only fetch new/updated pages)
- ✅ Supports multiple spaces or all spaces

## Prerequisites

1. **Confluence Cloud Instance** (not Server/Data Center)
   - Must be `https://yourcompany.atlassian.net`
   - OAuth 2.0 apps only work with Cloud

2. **Atlassian OAuth App** (recommended) or **API Token**

## Setup Options

### Option 1: OAuth 2.0 (Recommended for Production)

#### Step 1: Create OAuth App

1. Go to [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/)
2. Click **Create** → **OAuth 2.0 integration**
3. Name your app (e.g., "ContextDock")
4. Click **Permissions** → **Add** → **Confluence API**
5. Configure OAuth scopes:
   - `read:confluence-content.all` - Read all Confluence content
   - `read:confluence-space.summary` - Read space information
6. Click **Authorization** → **Add** callback URL:
   - For local testing: `http://localhost:8080/callback`
   - For production: `https://your-domain.com/api/v1/oauth/callback`
7. Save settings

#### Step 2: Get OAuth Token

**Using Authorization Code Flow (Web App):**

```bash
# 1. Get authorization URL
CLIENT_ID="your_client_id"
REDIRECT_URI="http://localhost:8080/callback"
SCOPES="read:confluence-content.all%20read:confluence-space.summary"
AUTH_URL="https://auth.atlassian.com/authorize?audience=api.atlassian.com&client_id=${CLIENT_ID}&scope=${SCOPES}&redirect_uri=${REDIRECT_URI}&response_type=code&prompt=consent"

# 2. Open URL in browser
open "$AUTH_URL"

# 3. After authorization, get code from callback URL
# 4. Exchange code for token
curl -X POST https://auth.atlassian.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "authorization_code",
    "client_id": "'"$CLIENT_ID"'",
    "client_secret": "'"$CLIENT_SECRET"'",
    "code": "'"$AUTH_CODE"'",
    "redirect_uri": "'"$REDIRECT_URI"'"
  }'
```

Response will contain `access_token` - save this!

#### Common OAuth Errors

**Error: "authorization_code is invalid"**

This error occurs when:
- ✅ **Code already used** - Authorization codes are single-use only. Get a new code.
- ✅ **Code expired** - Codes expire after ~10 minutes. Generate a new authorization URL.
- ✅ **Redirect URI mismatch** - The redirect_uri in token request must EXACTLY match the one in authorization request.
- ✅ **Wrong code copied** - Make sure you copied the entire code from the callback URL.

**Solution:**
1. Start over with a fresh authorization URL
2. Complete the flow quickly (within 10 minutes)
3. Copy the ENTIRE code from the URL parameter
4. Use it immediately for token exchange
5. Don't reuse the same code

**Quick OAuth Flow (Step-by-Step):**
```bash
# 1. Set your credentials
CLIENT_ID="your_client_id_here"
CLIENT_SECRET="your_client_secret_here"
REDIRECT_URI="http://localhost:8080/callback"

# 2. Generate authorization URL
echo "Open this URL in your browser:"
echo "https://auth.atlassian.com/authorize?audience=api.atlassian.com&client_id=${CLIENT_ID}&scope=read:confluence-content.all%20read:confluence-space.summary&redirect_uri=${REDIRECT_URI}&response_type=code&prompt=consent"

# 3. After authorization, you'll be redirected to:
# http://localhost:8080/callback?code=YOUR_CODE_HERE
# Copy the code value

# 4. Exchange code for token (replace YOUR_CODE with actual code)
AUTH_CODE="paste_your_code_here"
curl -X POST https://auth.atlassian.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "authorization_code",
    "client_id": "'"$CLIENT_ID"'",
    "client_secret": "'"$CLIENT_SECRET"'",
    "code": "'"$AUTH_CODE"'",
    "redirect_uri": "'"$REDIRECT_URI"'"
  }'
```

### Option 2: API Token (Quick Start - **RECOMMENDED FOR TESTING**)

**⚠️ Note:** API tokens are much easier to set up and don't expire. Perfect for testing!

#### Step 1: Create API Token

1. Go to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Give it a name (e.g., "ContextDock Test")
4. Copy the token immediately (you can't see it again!)

#### Step 2: Use API Token with Basic Auth

API tokens work with Basic Auth using your email + token:

```bash
# Set your credentials
export CONFLUENCE_EMAIL="your.email@company.com"
export CONFLUENCE_API_TOKEN="your_api_token_here"

# Encode for Basic Auth
export CONFLUENCE_ACCESS_TOKEN=$(echo -n "${CONFLUENCE_EMAIL}:${CONFLUENCE_API_TOKEN}" | base64)

# Now use CONFLUENCE_ACCESS_TOKEN in the connector
```

**Alternative - Let the connector handle encoding:**

Just provide the API token directly, and we'll handle the Basic Auth:

```bash
export CONFLUENCE_ACCESS_TOKEN="your_api_token_here"
export CONFLUENCE_EMAIL="your.email@company.com"  # Optional: for Basic Auth
```

## Testing Connection

### Quick Test (Recommended: Use API Token)

**Option A: API Token (Easiest)**
```bash
# 1. Create API token at: https://id.atlassian.com/manage-profile/security/api-tokens
# 2. Set credentials
export CONFLUENCE_INSTANCE_URL="https://yourcompany.atlassian.net"
export CONFLUENCE_EMAIL="your.email@company.com"
export CONFLUENCE_API_TOKEN="your_api_token_here"

# 3. Run test script
python test_confluence.py
```

**Option B: OAuth Token**
```bash
# If you already have an OAuth access token
export CONFLUENCE_INSTANCE_URL="https://yourcompany.atlassian.net"
export CONFLUENCE_ACCESS_TOKEN="your_oauth_access_token"

# Run test script
python test_confluence.py
```

Expected output:
```
Testing Confluence connection to: https://yourcompany.atlassian.net
------------------------------------------------------------

1️⃣  Testing spaces API...
✅ Found 3 spaces:
   • ENG: Engineering (global)
   • DOCS: Documentation (global)
   • PROD: Product (global)

2️⃣  Testing content API...
✅ Found 5 pages in space 'ENG':
   • 12345: API Design Guidelines (page)
   • 12346: Architecture Overview (page)
   ...

3️⃣  Testing page details...
✅ Page: API Design Guidelines (ID: 12345)
   Content preview: Our API design follows REST principles...

4️⃣  Testing cache loading...
✅ Loaded 3 spaces into cache

5️⃣  Testing sync (fetching first 3 pages)...
   ✅ Document 1: API Design Guidelines (space: ENG)
   ✅ Document 2: Architecture Overview (space: ENG)
   ✅ Document 3: Team Processes (space: ENG)

✅ Sync test complete: 3 documents

=============================================================
✅ All Confluence connector tests passed!
=============================================================
```

## Creating Connector in Database

### Setup Single Space

```bash
python setup_confluence.py setup \
  --instance-url https://yourcompany.atlassian.net \
  --access-token YOUR_TOKEN_HERE \
  --workspace-id 1 \
  --spaces ENG,DOCS
```

### Setup All Spaces

```bash
python setup_confluence.py setup \
  --instance-url https://yourcompany.atlassian.net \
  --access-token YOUR_TOKEN_HERE \
  --workspace-id 1
```

Expected output:
```
✅ Confluence connector created!
   Connector ID: 2
   Instance URL: https://yourcompany.atlassian.net
   Spaces: ENG, DOCS

Next step: python setup_confluence.py sync --connector-id 2
```

## Syncing Content

### Sync All Pages

```bash
python setup_confluence.py sync --connector-id 2 --all
```

### Sync Limited Pages (Testing)

```bash
python setup_confluence.py sync --connector-id 2 --max-pages 10
```

### Reindex (Delete and Re-sync)

```bash
python setup_confluence.py sync --connector-id 2 --reindex --all
```

Expected output:
```
Starting Confluence sync for connector 2
Instance URL: https://yourcompany.atlassian.net
Syncing spaces: ENG, DOCS

Loading Confluence spaces into cache
Loaded 2 spaces into cache

Syncing space: ENG
Progress: 10 pages synced, 10 indexed
Progress: 20 pages synced, 20 indexed
...

Syncing space: DOCS
Progress: 30 pages synced, 30 indexed
...

✅ Sync complete!
   Pages synced: 47
   Documents indexed: 47
```

## Testing Search

After syncing, test search functionality:

```bash
python test_search_api.py
```

Example queries:
- `"API design guidelines"`
- `"authentication flow"`
- `"deployment process"`

Expected result:
```json
{
  "query": "API design guidelines",
  "total": 5,
  "results": [
    {
      "title": "API Design Guidelines",
      "content": "Our API design follows REST principles...",
      "score": 0.87,
      "source_type": "confluence",
      "metadata": {
        "page_id": "12345",
        "space_key": "ENG",
        "space_name": "Engineering",
        "source_url": "https://yourcompany.atlassian.net/wiki/spaces/ENG/pages/12345"
      }
    }
  ]
}
```

## Using with Slack Bot

Once Confluence content is indexed, you can query it via Slack bot:

```
You: @contextdock What are our API design guidelines?

ContextDock: 🔍 Search Results for: What are our API design guidelines?
Found 3 results • Took 234ms

1. API Design Guidelines
Our API design follows REST principles with consistent naming...
📈 Relevance: 89.2%
💬 #engineering
👤 John Doe
🔗 View in Confluence

2. REST API Best Practices
...
```

## Configuration Options

### Connector Config

```json
{
  "instance_url": "https://yourcompany.atlassian.net",
  "space_keys": ["ENG", "DOCS", "PRODUCT"]  // Optional: leave empty for all spaces
}
```

### Sync Schedule

- `hourly` - Sync every hour (high-activity spaces)
- `6-hourly` - Sync every 6 hours (default, recommended)
- `daily` - Sync once per day (low-activity spaces)

### Rate Limits

Confluence Cloud enforces:
- **10 requests per second** (standard tier)
- **200 requests per minute** (backup limit)

The connector automatically handles rate limiting with retry logic.

## Troubleshooting

### Error: "instance_url is required"

Make sure your connector config includes:
```json
{
  "instance_url": "https://yourcompany.atlassian.net"
}
```

### Error: "401 Unauthorized"

1. **OAuth token expired** - Tokens expire after 1 hour by default
   - For testing: Just generate a new token (quickest)
   - For production: Implement token refresh logic
   - **OR use API token** (doesn't expire!)

2. **Wrong token type** - Make sure you're using:
   - OAuth access token (starts with `eyJ...`)
   - OR API token (random string)
   - NOT the client secret or client ID

3. **Insufficient permissions** - Verify OAuth scopes:
   - `read:confluence-content.all`
   - `read:confluence-space.summary`

4. **API Token with wrong format**:
   - Use Basic Auth: `base64(email:api_token)`
   - Or provide email separately and let connector handle it

### Error: "authorization_code is invalid" (OAuth)

See [Common OAuth Errors](#common-oauth-errors) section above.

**Quick fix:** Use API Token instead of OAuth for testing:
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Create token
3. Export: `export CONFLUENCE_API_TOKEN="your_token"`
4. Run test: `python test_confluence.py`

### Error: "403 Forbidden"

Page or space is restricted. The connector will:
- Skip restricted pages you don't have access to
- Log warnings for inaccessible content
- Continue syncing accessible pages

### Error: "No spaces found"

1. Check your Confluence instance URL is correct
2. Verify you have access to at least one space
3. Try accessing Confluence web interface with same credentials

### Slow sync / Timeout

For large Confluence instances (1000+ pages):

1. **Sync specific spaces only**:
   ```bash
   --spaces ENG,DOCS
   ```

2. **Use incremental sync** (after first full sync):
   - Only fetches pages modified since last sync
   - Much faster for subsequent runs

3. **Adjust rate limits** if you have premium tier:
   ```python
   # In connector.py
   RATE_LIMIT_CALLS = 20  # Increase for premium
   ```

## Architecture

### Data Flow

```
Confluence Cloud (HTTPS API)
    ↓
ConfluenceConnector (OAuth/API Token)
    ↓
Fetch: Spaces → Pages → Content → Restrictions
    ↓
Parse: HTML → Text, Extract Metadata
    ↓
PostgreSQL (Raw documents)
    ↓
OpenAI API (Generate embeddings)
    ↓
Qdrant (Vector embeddings)
    ↓
Search API / Slack Bot (Query)
```

### Connector Structure

```
src/connectors/confluence/
├── __init__.py          # Connector definition & plugin interface
├── connector.py         # Main connector implementation
│   ├── _fetch_spaces_page()      # GET /api/space
│   ├── _fetch_pages_page()       # GET /api/content
│   ├── _fetch_page_restrictions() # GET /api/content/{id}/restriction
│   ├── _load_spaces_cache()      # Cache space metadata
│   ├── sync()                     # Main sync loop
│   └── extract_acl()              # Extract permissions
└── acl.py               # ACL extraction utilities
```

### Database Schema

**Connectors Table:**
```sql
id: 2
connector_type: "confluence"
name: "Confluence"
config_json: {"instance_url": "...", "space_keys": [...]}
credentials: {"access_token": "...", "refresh_token": "..."}
sync_schedule: "6-hourly"
is_active: true
```

**Documents Table:**
```sql
id: 123
connector_id: 2
workspace_id: 1
source_id: "confluence_12345"
source_type: "confluence"
title: "API Design Guidelines"
content: "Our API design follows..."
metadata_json: {
  "page_id": "12345",
  "space_key": "ENG",
  "space_name": "Engineering",
  "version": 3,
  "last_modified": "2026-01-09T10:30:00Z",
  "source_url": "https://..."
}
acl_metadata: {
  "space_key": "ENG",
  "access_level": "space",
  "requires_space_permission": true
}
```

## API Reference

### Confluence REST API v1

**Base URL:** `https://yourcompany.atlassian.net/wiki/rest/api`

**Endpoints Used:**
- `GET /space` - List spaces
- `GET /content` - List pages/blogs
- `GET /content/{id}` - Get page details
- `GET /content/{id}/restriction` - Get page restrictions

**Documentation:** https://developer.atlassian.com/cloud/confluence/rest/v1/intro/

## Next Steps

1. ✅ Set up Confluence connector
2. ✅ Sync pages and index content
3. 🔄 Test search functionality
4. 🔄 Try queries via Slack bot
5. 📅 Schedule regular syncs (Celery worker)
6. 🔐 Implement OAuth refresh token flow
7. 📊 Monitor sync performance and errors

## Production Checklist

- [ ] Use OAuth 2.0 (not API tokens)
- [ ] Implement token refresh logic
- [ ] Set up scheduled sync (Celery)
- [ ] Configure space filters (don't sync everything)
- [ ] Monitor Confluence rate limits
- [ ] Set up error alerting
- [ ] Test ACL enforcement (permission-aware search)
- [ ] Document space selection strategy
- [ ] Plan for large page content (>100KB)
- [ ] Handle attachments (optional)

## Resources

- [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/)
- [Confluence Cloud REST API](https://developer.atlassian.com/cloud/confluence/rest/v1/intro/)
- [OAuth 2.0 (3LO) Guide](https://developer.atlassian.com/cloud/confluence/oauth-2-3lo-apps/)
- [API Token Management](https://id.atlassian.com/manage-profile/security/api-tokens)

## Support

If you encounter issues:
1. Check logs: `tail -f logs/contextdock.log`
2. Run test script: `python test_confluence.py`
3. Verify credentials and permissions
4. Check Confluence API status: https://status.developer.atlassian.com/
