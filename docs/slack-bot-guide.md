# How to Use ContextDock Bot in Slack

This guide shows you how to set up and use the ContextDock bot to search your workspace knowledge directly from Slack.

## Quick Start

Once configured, you can query ContextDock in three ways:

### 1. @Mention the Bot (Recommended)

In any channel where the bot is present:

```
@contextdock what are the user engagement ideas?
@contextdock show me proposals about sleep tracking
@contextdock find discussions about ContextDock implementation
```

### 2. Direct Message

Send a DM to the ContextDock bot:

```
user engagement strategies
sleep tracking features
app improvement ideas
```

### 3. Slash Command

Use the `/contextdock` slash command anywhere:

```
/contextdock search user engagement ideas
/contextdock search ContextDock implementation
/contextdock search app features
```

---

## Setup Instructions

### Prerequisites

You already have:
- ✅ Slack app created at https://api.slack.com/apps
- ✅ Bot token (stored in `.env` as `SLACK_BOT_TOKEN`)
- ✅ Bot invited to #ideas channel
- ✅ Messages indexed (196 from #ideas)

### Step 1: Get Signing Secret

1. Go to https://api.slack.com/apps
2. Select your **ContextDock** app
3. Navigate to **Basic Information** → **App Credentials**
4. Copy **Signing Secret**
5. Add to your `.env` file:

```bash
SLACK_SIGNING_SECRET=your_signing_secret_here
```

### Step 2: Enable Event Subscriptions

1. In your Slack app settings, go to **Event Subscriptions**
2. Toggle **Enable Events** to **ON**
3. Set **Request URL**: 
   ```
   https://your-public-domain.com/api/v1/slack/events
   ```
   
   **For local development**, use ngrok:
   ```bash
   ngrok http 8001
   # Use the https URL: https://abc123.ngrok.io/api/v1/slack/events
   ```

4. Under **Subscribe to bot events**, add:
   - `app_mention` - When someone @mentions your bot
   - `message.im` - When someone DMs your bot

5. Click **Save Changes**

### Step 3: Create Slash Command

1. Go to **Slash Commands**
2. Click **Create New Command**
3. Fill in:
   - **Command**: `/contextdock`
   - **Request URL**: `https://your-domain.com/api/v1/slack/commands`
   - **Short Description**: `Search ContextDock knowledge base`
   - **Usage Hint**: `search <your query>`
4. Click **Save**

### Step 4: Reinstall App

After making these changes:

1. Go to **Install App** (or **OAuth & Permissions**)
2. Click **Reinstall to Workspace**
3. Authorize the permissions

### Step 5: Update API Routes

Register the Slack bot routes in `src/main.py`:

```python
from src.api.routes import connectors, conversations, query, search, slack_bot

# Include routers
app.include_router(slack_bot.router, prefix="/api")
```

### Step 6: Restart Your Server

```bash
# Stop existing server (Ctrl+C)
# Start with updated routes
source .venv/bin/activate
uvicorn src.main:app --reload --port 8001
```

### Step 7: Verify Setup

Test the bot health endpoint:

```bash
curl http://localhost:8001/api/v1/slack/health
```

Expected response:
```json
{
    "status": "ready",
    "bot_token": "configured",
    "signing_secret": "configured"
}
```

---

## Usage Examples

### In Channels

Invite the bot to a channel first:
```
/invite @contextdock
```

Then query it:
```
@contextdock what are the latest user engagement strategies?
```

### In Direct Messages

1. Start a DM with **ContextDock**
2. Type your query:
```
show me ideas about sleep tracking
```

### With Slash Commands

From any channel or DM:
```
/contextdock search app improvement proposals
```

---

## Response Format

The bot returns results in this format:

```
🔍 Search Results for: `user engagement ideas`
Found 25 results (showing 5) • Took 612ms
────────────────────────────────────────

1. Rethinking User Engagement Flow
📈 Relevance: 55.25%
💬 #ideas • 👤 hilar
View in Slack

2. Data driven nudges
📈 Relevance: 51.55%
💬 #ideas • 👤 Vijay
View in Slack

[... more results ...]

Showing top 5 of 25 results. Refine your query for more specific results.
```

---

## Advanced Configuration

### Adjust Result Count

Edit `src/integrations/slack_bot.py`:

```python
results = search_contextdock(query, limit=10, min_score=0.3)
```

- `limit`: Number of results (default: 5)
- `min_score`: Minimum relevance threshold 0.0-1.0 (default: 0.3)

### Custom Response Templates

Modify `format_search_results()` in `src/integrations/slack_bot.py` to customize:
- Result formatting
- Emojis
- Metadata displayed
- Link styles

---

## Troubleshooting

### Bot Doesn't Respond

1. **Check bot is invited to channel**:
   ```
   /invite @contextdock
   ```

2. **Verify event subscriptions are enabled**:
   - Go to app settings → Event Subscriptions
   - Ensure URL is verified (green checkmark)

3. **Check server logs**:
   ```bash
   # Check API server logs
   tail -f logs/api.log
   ```

### "Invalid Request Signature" Error

- Verify `SLACK_SIGNING_SECRET` in `.env` matches the one in your Slack app settings
- Restart the API server after updating `.env`

### Bot Responds But Shows No Results

1. **Verify search API is working**:
   ```bash
   curl -X POST http://localhost:8001/api/v1/search \
     -H "Content-Type: application/json" \
     -d '{"query": "test", "limit": 5}'
   ```

2. **Check indexed documents**:
   ```bash
   curl http://localhost:8001/api/v1/search/stats
   ```

3. **Sync more channels**:
   ```bash
   python sync_slack_messages.py --channel CHANNEL_ID
   ```

### ngrok URL Expired

If using ngrok for local development:

1. Restart ngrok:
   ```bash
   ngrok http 8001
   ```

2. Update Slack app URLs with new ngrok URL
3. Re-verify the Event Subscriptions URL

---

## Production Deployment

For production, instead of ngrok:

1. Deploy your API to a public server (AWS, GCP, Heroku, etc.)
2. Use your production domain:
   ```
   https://api.yourcompany.com/api/v1/slack/events
   ```
3. Ensure SSL/TLS is enabled (required by Slack)
4. Set up proper logging and monitoring

---

## Tips & Best Practices

### For Better Results

- **Be specific**: "user engagement ideas for mobile apps" vs "engagement"
- **Use natural language**: "What are the proposals about sleep tracking?"
- **Mention keywords**: Include important terms from your documents

### Privacy & Security

- DMs are private - results only visible to you
- @mentions in channels - results visible to everyone
- Slash commands - use `response_type: "ephemeral"` for private results

### Performance

- Typical query time: 300-800ms
- Cached results for common queries
- Index more channels for broader search coverage

---

## Next Steps

1. ✅ Invite bot to more channels:
   ```
   /invite @contextdock
   ```
   in #general, #backend, #bugs, etc.

2. ✅ Sync those channels:
   ```bash
   python sync_slack_messages.py --all
   ```

3. ✅ Test queries to ensure good results

4. ✅ Train your team to use the bot

5. ✅ Add Confluence and Jira connectors for broader knowledge coverage

---

## Support

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review API logs: `tail -f logs/api.log`
3. Test search API directly: `python test_search_api.py --interactive`
4. Verify Slack app configuration at https://api.slack.com/apps

Happy searching! 🚀
