# Search API Documentation

The ContextDock Search API provides semantic search capabilities over indexed documents from Slack, Confluence, Jira, and other connected sources.

## Base URL

```
http://localhost:8001/api/v1
```

## Authentication

Currently using workspace-based authentication (TODO: Implement JWT auth).

## Endpoints

### POST /search

Perform semantic search across all indexed documents.

**Request Body:**

```json
{
  "query": "user engagement strategies",
  "limit": 10,
  "offset": 0,
  "channel_id": "CGREG0X9A",
  "source_type": "slack",
  "min_score": 0.0
}
```

**Parameters:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | - | Natural language search query (1-1000 chars) |
| `limit` | integer | No | 10 | Maximum results to return (1-100) |
| `offset` | integer | No | 0 | Number of results to skip (pagination) |
| `channel_id` | string | No | null | Filter by Slack channel ID |
| `source_type` | string | No | null | Filter by source type (slack, confluence, jira) |
| `min_score` | float | No | 0.0 | Minimum relevance score threshold (0.0-1.0) |

**Response:**

```json
{
  "query": "user engagement strategies",
  "total": 25,
  "limit": 10,
  "offset": 0,
  "results": [
    {
      "id": 5,
      "title": "Rethinking User Engagement Flow",
      "content": "Channel: #ideas\nUser: hilar\nDate: 2025-09-17...",
      "url": "https://slack.com/archives/CGREG0X9A/p1758100424009149",
      "score": 0.5525,
      "metadata": {
        "source_type": "slack",
        "source_id": "slack_CGREG0X9A_1758100424.009149",
        "channel_id": "CGREG0X9A",
        "channel_name": "ideas",
        "user_id": "UKLGQ1142",
        "username": "hilar",
        "message_ts": "1758100424.009149",
        "created_at": null
      }
    }
  ],
  "took_ms": 853.15
}
```

**Status Codes:**

- `200 OK` - Search completed successfully
- `422 Unprocessable Entity` - Invalid request parameters
- `500 Internal Server Error` - Search service error

---

### GET /search/stats

Get search index statistics for the current workspace.

**Response:**

```json
{
  "total_documents": 196,
  "total_chunks": 196,
  "vector_dimensions": 1536,
  "sources": {
    "slack": 196
  },
  "last_indexed": "2026-01-08T19:04:34.461931Z"
}
```

**Status Codes:**

- `200 OK` - Stats retrieved successfully
- `500 Internal Server Error` - Database error

---

### GET /search/health

Check search service health status.

**Response:**

```json
{
  "status": "healthy",
  "openai": "configured",
  "qdrant": "ready"
}
```

**Status Values:**

- `status`: `healthy` | `degraded` | `unhealthy`
- `openai`: `configured` | `not_configured` | `error`
- `qdrant`: `ready` | `collection_missing` | `error`

**Status Codes:**

- `200 OK` - Health check completed

---

## Usage Examples

### cURL

**Basic Search:**

```bash
curl -X POST http://localhost:8001/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "user engagement ideas",
    "limit": 5
  }'
```

**With Filters:**

```bash
curl -X POST http://localhost:8001/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "ContextDock implementation",
    "limit": 3,
    "min_score": 0.5,
    "channel_id": "CGREG0X9A"
  }'
```

**Pagination:**

```bash
# Page 1 (results 0-9)
curl -X POST http://localhost:8001/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "app features",
    "limit": 10,
    "offset": 0
  }'

# Page 2 (results 10-19)
curl -X POST http://localhost:8001/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "app features",
    "limit": 10,
    "offset": 10
  }'
```

### Python

```python
import requests

# Basic search
response = requests.post(
    "http://localhost:8001/api/v1/search",
    json={
        "query": "user engagement strategies",
        "limit": 5,
    }
)
results = response.json()

# Process results
for result in results["results"]:
    print(f"Score: {result['score']:.4f}")
    print(f"Title: {result['title']}")
    print(f"URL: {result['url']}\n")
```

### JavaScript

```javascript
// Basic search
const response = await fetch('http://localhost:8001/api/v1/search', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    query: 'user engagement strategies',
    limit: 5,
  }),
});

const results = await response.json();

// Process results
results.results.forEach(result => {
  console.log(`Score: ${result.score.toFixed(4)}`);
  console.log(`Title: ${result.title}`);
  console.log(`URL: ${result.url}\n`);
});
```

---

## Query Tips

### Natural Language

The search API understands natural language queries:

- ✅ "What are the user engagement ideas?"
- ✅ "Show me proposals about sleep tracking"
- ✅ "Find discussions about ContextDock implementation"

### Keywords

You can also use simple keywords:

- ✅ "user engagement"
- ✅ "sleep tracking"
- ✅ "app features"

### Relevance Scores

Scores range from 0.0 to 1.0:

- **0.7-1.0**: Highly relevant (exact match or very similar)
- **0.5-0.7**: Moderately relevant (related concepts)
- **0.3-0.5**: Loosely relevant (tangential mentions)
- **0.0-0.3**: Weakly relevant (minimal similarity)

Use `min_score` to filter out low-relevance results.

---

## Rate Limits

Currently no rate limits enforced (development environment).

Production limits (TODO):
- 100 requests per minute per workspace
- 1000 requests per hour per workspace

---

## Error Handling

All errors return a JSON response:

```json
{
  "detail": "Error message"
}
```

**Common Errors:**

- `422 Unprocessable Entity` - Invalid query (empty, too long)
- `500 Internal Server Error` - Vector search failed, embedding generation failed

---

## Semantic Search Technology

The search API uses:

- **OpenAI text-embedding-3-small** (1536 dimensions) for query and document embeddings
- **Qdrant** vector database for similarity search with COSINE distance
- **PostgreSQL** for document metadata storage

Results are ranked by cosine similarity between query and document embeddings.

---

## Interactive API Documentation

Visit http://localhost:8001/docs for interactive Swagger UI documentation where you can test API endpoints directly in your browser.
