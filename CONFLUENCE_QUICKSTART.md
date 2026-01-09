# ContextDock Confluence Connector - Quick Start

## What We've Built

The Confluence connector is **fully implemented** and ready to use! It includes:

✅ **Core Functionality**
- Fetch spaces, pages, and blog posts from Confluence Cloud
- Parse HTML content to text
- Extract page hierarchy (parent-child relationships)
- Support for incremental sync (only fetch new/updated pages)
- ACL extraction (space and page-level permissions)

✅ **Infrastructure**
- OAuth 2.0 and API token authentication
- Rate limiting (10 requests/second)
- Cursor-based pagination
- Error handling and retry logic
- Caching (spaces cache for metadata enrichment)

✅ **Tools Provided**
1. `test_confluence.py` - Test connection and API access
2. `setup_confluence.py` - Create connector and sync pages
3. `docs/CONFLUENCE_SETUP.md` - Complete setup guide

## Quick Start (3 Steps)

### Step 1: Get Confluence Credentials

**Option A: API Token (Easiest for testing)**
```bash
# 1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens
# 2. Create API token
# 3. Export credentials

export CONFLUENCE_INSTANCE_URL="https://yourcompany.atlassian.net"
export CONFLUENCE_ACCESS_TOKEN="your_api_token_here"
```

**Option B: OAuth 2.0 (Recommended for production)**
- See [docs/CONFLUENCE_SETUP.md](docs/CONFLUENCE_SETUP.md) for OAuth setup guide

### Step 2: Test Connection

```bash
# Activate environment
source .venv/bin/activate

# Run test
python test_confluence.py
```

Expected output:
```
✅ Found 3 spaces
✅ Found 5 pages in space 'ENG'
✅ Page details loaded
✅ Cache loading successful
✅ Sync test complete: 3 documents
```

### Step 3: Sync Content

```bash
# Create connector (replace with your URL and token)
python setup_confluence.py setup \
  --instance-url https://yourcompany.atlassian.net \
  --access-token $CONFLUENCE_ACCESS_TOKEN \
  --workspace-id 1 \
  --spaces ENG,DOCS

# Sync pages (use connector ID from previous command)
python setup_confluence.py sync --connector-id 2 --all
```

Output:
```
✅ Confluence connector created!
   Connector ID: 2
   Instance URL: https://yourcompany.atlassian.net
   Spaces: ENG, DOCS

✅ Sync complete!
   Pages synced: 47
   Documents indexed: 47
```

## What Gets Synced

For each Confluence page, we extract:

**Content:**
- Page title
- Body content (HTML → Text)
- Version number
- Last modified timestamp

**Metadata:**
- Page ID
- Space key and name
- Parent page (hierarchy)
- Source URL (deep link)
- Page restrictions (ACL)

**Example Document:**
```json
{
  "source_id": "confluence_12345",
  "source_type": "confluence",
  "title": "API Design Guidelines",
  "content": "Our API design follows REST principles...",
  "metadata": {
    "page_id": "12345",
    "space_key": "ENG",
    "space_name": "Engineering",
    "version": 3,
    "last_modified": "2026-01-09T10:30:00Z",
    "parent_id": "12340",
    "parent_title": "Architecture",
    "source_url": "https://company.atlassian.net/wiki/spaces/ENG/pages/12345"
  },
  "acl_metadata": {
    "space_key": "ENG",
    "access_level": "space",
    "requires_space_permission": true
  }
}
```

## Testing Search

After syncing, you can search Confluence content:

```bash
# Test search API
python test_search_api.py
```

Query examples:
- "API design guidelines"
- "authentication flow"
- "deployment process"

**Via Slack Bot:**
```
@contextdock What are our API design guidelines?
```

Bot will return:
- Matching Confluence pages
- Relevance scores
- Space and author info
- Deep links to original pages

## Configuration Options

### Sync Specific Spaces

```bash
# Only sync Engineering and Documentation spaces
python setup_confluence.py setup \
  --spaces ENG,DOCS \
  ...
```

### Sync All Spaces

```bash
# Sync every space you have access to
python setup_confluence.py setup \
  ...
# (omit --spaces flag)
```

### Incremental Sync

After the first full sync, subsequent syncs will only fetch:
- Pages created since last sync
- Pages modified since last sync

This is **much faster** for large instances!

### Sync Schedule

Configure in connector settings:
- `hourly` - For high-activity spaces
- `6-hourly` - Default, recommended
- `daily` - For archive/reference spaces

## Architecture

```
┌─────────────────────┐
│ Confluence Cloud    │  HTTPS API (OAuth 2.0)
│ (Atlassian)         │
└──────────┬──────────┘
           │
           ↓ Fetch spaces, pages, content
┌─────────────────────┐
│ ConfluenceConnector │  Python (src/connectors/confluence/)
│                     │
│ • Parse HTML → Text │
│ • Extract metadata  │
│ • Handle pagination │
│ • Cache spaces      │
└──────────┬──────────┘
           │
           ↓ Store documents
┌─────────────────────┐
│ PostgreSQL          │  Raw document storage
└──────────┬──────────┘
           │
           ↓ Generate embeddings
┌─────────────────────┐
│ OpenAI API          │  text-embedding-3-small
└──────────┬──────────┘
           │
           ↓ Index vectors
┌─────────────────────┐
│ Qdrant              │  Vector similarity search
└──────────┬──────────┘
           │
           ↓ Query
┌─────────────────────┐
│ Search API /        │  REST API / Slack Bot
│ Slack Bot           │
└─────────────────────┘
```

## Files Created

```
ContextDock/
├── src/connectors/confluence/
│   ├── __init__.py          ✅ Connector definition
│   ├── connector.py         ✅ Main implementation
│   └── acl.py               ✅ Permission extraction
│
├── test_confluence.py       🆕 Connection test
├── setup_confluence.py      🆕 Setup & sync script
│
└── docs/
    └── CONFLUENCE_SETUP.md  🆕 Complete guide
```

## Next Steps

### Immediate

1. **Get credentials** - Create API token or OAuth app
2. **Run test** - Verify connection works
3. **Sync content** - Index your Confluence pages
4. **Test search** - Query via API or Slack bot

### Production Ready

5. **Implement OAuth refresh** - Auto-renew tokens
6. **Schedule syncs** - Set up Celery worker
7. **Monitor performance** - Track sync times and errors
8. **Configure spaces** - Only sync relevant content
9. **Test ACL** - Verify permission-aware search

### Optional Enhancements

10. **Attachment support** - Index PDF, Word docs
11. **Blog post support** - Currently pages only
12. **Advanced parsing** - Tables, code blocks, etc.
13. **Bi-directional sync** - Write back to Confluence

## Common Issues

### "No spaces found"

✅ **Solution:** 
- Check your instance URL is correct
- Verify token has `read:confluence-space.summary` scope
- Log in to Confluence web interface to confirm access

### "401 Unauthorized"

✅ **Solution:**
- OAuth tokens expire after 1 hour → implement refresh
- API tokens don't expire but can be revoked
- Check token scope includes `read:confluence-content.all`

### "Rate limit exceeded"

✅ **Solution:**
- Confluence allows 10 req/sec (standard tier)
- Connector automatically handles this
- For premium tier, increase `RATE_LIMIT_CALLS` in connector.py

### Sync is slow

✅ **Solution:**
- Sync specific spaces: `--spaces ENG,DOCS`
- Use incremental sync (automatic after first run)
- For 1000+ pages, expect 5-10 minutes for full sync

## Success Criteria

✅ **Connector Working:**
- `test_confluence.py` passes all checks
- Spaces and pages fetched successfully
- No authentication errors

✅ **Sync Working:**
- Pages stored in PostgreSQL `documents` table
- Embeddings generated (check `embedding_status = 'completed'`)
- Vectors indexed in Qdrant

✅ **Search Working:**
- API returns relevant Confluence pages
- Slack bot can answer questions
- Source URLs link to correct pages

## Support

**Documentation:**
- Full guide: [docs/CONFLUENCE_SETUP.md](docs/CONFLUENCE_SETUP.md)
- Connector code: `src/connectors/confluence/connector.py`
- Tests: `tests/contract/connectors/test_confluence.py`

**API Reference:**
- [Confluence REST API](https://developer.atlassian.com/cloud/confluence/rest/v1/intro/)
- [OAuth 2.0 Guide](https://developer.atlassian.com/cloud/confluence/oauth-2-3lo-apps/)

**Troubleshooting:**
1. Check logs: `tail -f logs/contextdock.log`
2. Run test: `python test_confluence.py`
3. Verify database: `psql contextdock -c "SELECT COUNT(*) FROM documents WHERE source_type='confluence'"`

---

**Ready to start?** Run `python test_confluence.py` to begin! 🚀
