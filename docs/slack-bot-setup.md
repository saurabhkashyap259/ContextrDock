# Slack Bot Setup & Testing Guide

## Current Status

✅ **Completed Implementation:**
- Search handler functions added to `src/integrations/slack_bot.py`
- API routes registered in `src/main.py` at `/api/v1/slack/*`
- Environment variables configured in `.env`
- 196 documents indexed from #ideas channel

⏳ **Manual Configuration Needed:**
1. Add Slack Signing Secret to `.env`
2. Set up public URL (ngrok for local testing)
3. Configure Slack App Event Subscriptions
4. Configure Slack Slash Command
5. Test bot interactions

---

## Step 1: Get Slack Signing Secret

1. Go to https://api.slack.com/apps
2. Select your **ContextDock** app
3. Navigate to **Basic Information** → **App Credentials**
4. Copy the **Signing Secret**
5. Add to your `.env` file:

```bash
SLACK_SIGNING_SECRET=your_actual_signing_secret_here
```

6. Save the file

---

## Step 2: Set Up Public URL (Local Testing)

Your Slack app needs a public HTTPS URL to send webhooks to your local API.

### Option A: Using ngrok (Recommended for Development)

1. **Install ngrok** (if not already installed):
   ```bash
   brew install ngrok
   # OR download from https://ngrok.com/download
   ```

2. **Start ngrok tunnel**:
   ```bash
   ngrok http 8001
   ```

3. **Copy the HTTPS URL** from the output:
   ```
   Forwarding  https://abc123xyz.ngrok.io -> http://localhost:8001
   ```
   
   Copy: `https://abc123xyz.ngrok.io`

4. **Keep ngrok running** in this terminal window

### Option B: Using Cloudflare Tunnel

```bash
# Install Cloudflare Tunnel
brew install cloudflare/cloudflare/cloudflared

# Start tunnel
cloudflared tunnel --url http://localhost:8001
```

---

## Step 3: Configure Slack App Event Subscriptions

1. Go to https://api.slack.com/apps
2. Select your **ContextDock** app
3. Click **Event Subscriptions** in the sidebar

### Enable Events

4. Toggle **Enable Events** to **ON**

### Set Request URL

5. In the **Request URL** field, enter:
   ```
   https://your-ngrok-url.ngrok.io/api/v1/slack/events
   ```
   
   Example: `https://abc123xyz.ngrok.io/api/v1/slack/events`

6. Slack will send a **URL verification challenge**
   - Wait for the green "Verified" checkmark ✅
   - If verification fails, check:
     - Is your API server running? (`uvicorn src.main:app --reload --port 8001`)
     - Is ngrok running and forwarding to port 8001?
     - Is SLACK_SIGNING_SECRET set in `.env`?

### Subscribe to Bot Events

7. Scroll down to **Subscribe to bot events**
8. Click **Add Bot User Event** and add:
   - `app_mention` - When users @mention your bot
   - `message.im` - When users send DMs to your bot

9. Click **Save Changes**

### Reinstall App

10. Slack will show a banner: **"You need to reinstall your app"**
11. Click **reinstall your app** and authorize the new permissions

---

## Step 4: Configure Slash Command

1. In your Slack app settings, click **Slash Commands** in the sidebar
2. Click **Create New Command**

### Command Configuration

3. Fill in the form:
   - **Command**: `/contextdock`
   - **Request URL**: `https://your-ngrok-url.ngrok.io/api/v1/slack/commands`
   - **Short Description**: `Search ContextDock knowledge base`
   - **Usage Hint**: `search <your query>`
   - **Escape channels, users, and links**: ✅ (checked)

4. Click **Save**

---

## Step 5: Restart Your API Server

After adding SLACK_SIGNING_SECRET to .env:

```bash
# If server is running, stop it (Ctrl+C)

# Restart with environment variables loaded
cd /Users/saurabhkashyap/personal/ContextDock
source .venv/bin/activate
uvicorn src.main:app --reload --port 8001
```

---

## Step 6: Verify Setup

### Test Health Endpoint

```bash
curl http://localhost:8001/api/v1/slack/health
```

**Expected Response:**
```json
{
    "status": "ready",
    "bot_token": "configured",
    "signing_secret": "configured"
}
```

If you see `"signing_secret": "not_configured"`, check that:
- SLACK_SIGNING_SECRET is set in `.env`
- You restarted the API server after adding it

### Check API Documentation

Open in browser: http://localhost:8001/docs

Verify you see these new endpoints:
- `POST /api/v1/slack/events`
- `POST /api/v1/slack/commands`
- `GET /api/v1/slack/health`

---

## Step 7: Test Bot Interactions

### Test 1: @Mention in Channel

1. Go to your Slack workspace
2. Navigate to **#ideas** channel (where the bot is already invited)
3. Type and send:
   ```
   @contextdock what are the user engagement ideas?
   ```

**Expected Behavior:**
- Bot shows "🔍 Searching..." briefly
- Bot updates message with formatted search results
- Results show:
  - Title and relevance score
  - Channel name and user
  - "View in Slack" links

**Troubleshooting:**
- **No response**: Check API logs for errors: `tail -f logs/api.log`
- **"Invalid signature"**: Verify SLACK_SIGNING_SECRET matches Slack app settings
- **"Search API error"**: Ensure search API is working: `curl -X POST http://localhost:8001/api/v1/search -H "Content-Type: application/json" -d '{"query":"test","limit":5}'`

### Test 2: Direct Message

1. In Slack, click **Direct messages** → **Add teammates**
2. Search for **ContextDock** and start a DM
3. Type and send:
   ```
   user engagement strategies
   ```

**Expected Behavior:**
- Same search results as @mention
- Response is private (only you see it)

### Test 3: Slash Command

1. In **any channel** (including #ideas), type:
   ```
   /contextdock search sleep tracking
   ```
2. Press Enter

**Expected Behavior:**
- Results appear only to you (ephemeral message)
- If no query provided: Shows help message

### Test 4: Help Messages

Test empty queries:
```
@contextdock
/contextdock
```

**Expected:** Help message with usage examples

---

## Step 8: Add Bot to More Channels (Optional)

To search across more channels:

1. **Invite bot to channels**:
   ```
   # In #general
   /invite @contextdock
   
   # In #backend
   /invite @contextdock
   ```

2. **Sync those channels**:
   ```bash
   cd /Users/saurabhkashyap/personal/ContextDock
   source .venv/bin/activate
   
   # Sync all channels the bot can access
   python sync_slack_messages.py --all
   ```

3. **Verify indexed documents**:
   ```bash
   curl http://localhost:8001/api/v1/search/stats
   ```

---

## Common Issues & Solutions

### Issue: Bot doesn't respond to @mentions

**Diagnosis:**
```bash
# Check API logs
tail -f logs/api.log

# Test event webhook directly
curl -X POST http://localhost:8001/api/v1/slack/events \
  -H "Content-Type: application/json" \
  -d '{"type":"url_verification","challenge":"test123"}'
```

**Solutions:**
- Verify Event Subscriptions URL is verified (green checkmark) in Slack app settings
- Check ngrok is still running (URLs expire after 2 hours on free tier)
- Restart API server with correct SLACK_SIGNING_SECRET

### Issue: "Invalid Request Signature" Error

**Cause:** SLACK_SIGNING_SECRET mismatch

**Solution:**
1. Go to https://api.slack.com/apps → Your App → Basic Information
2. Copy the **Signing Secret** (not Client Secret!)
3. Update `.env`: `SLACK_SIGNING_SECRET=correct_value_here`
4. Restart API server

### Issue: Search returns no results

**Diagnosis:**
```bash
# Check indexed documents
curl http://localhost:8001/api/v1/search/stats

# Test search directly
python test_search_api.py --demo
```

**Solutions:**
- If `documents: 0`: Run `python sync_slack_messages.py`
- If documents exist but query fails: Check OpenAI API key
- Try broader queries: "ideas" instead of "very specific phrase"

### Issue: ngrok URL expired

**Cause:** Free ngrok URLs expire after a few hours

**Solution:**
1. Restart ngrok: `ngrok http 8001`
2. Copy new URL: `https://new-url.ngrok.io`
3. Update both:
   - Event Subscriptions Request URL
   - Slash Command Request URL
4. Save changes and re-verify

---

## Production Deployment

For production (not localhost):

### 1. Deploy API to Cloud

Deploy your API to a server with a permanent URL:
- **AWS**: EC2 + ALB, ECS, App Runner
- **GCP**: Cloud Run, GKE
- **Azure**: App Service, AKS
- **Heroku**: `git push heroku main`
- **Render**: Connect GitHub repo

### 2. Update Slack App URLs

Replace ngrok URL with your production URL:
```
https://api.yourcompany.com/api/v1/slack/events
https://api.yourcompany.com/api/v1/slack/commands
```

### 3. Enable HTTPS

Slack requires HTTPS endpoints. Most cloud platforms provide this automatically.

### 4. Set Environment Variables

Set production environment variables:
```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://...
QDRANT_URL=https://...
```

---

## Testing Checklist

Before marking setup complete, verify:

- [ ] SLACK_SIGNING_SECRET added to `.env`
- [ ] API server running on port 8001
- [ ] ngrok (or tunnel) running and forwarding to 8001
- [ ] Event Subscriptions URL verified (green checkmark)
- [ ] Slash Command created and saved
- [ ] Health endpoint returns `status: "ready"`
- [ ] @mention in #ideas returns search results
- [ ] DM to bot returns search results
- [ ] `/contextdock search test` returns results
- [ ] Results show relevance scores, channels, users
- [ ] "View in Slack" links work

---

## Next Steps

After successful bot setup:

1. ✅ **Train your team** - Share usage examples in #general
2. ✅ **Expand coverage** - Add bot to more channels and sync
3. ✅ **Add connectors** - Integrate Confluence, Jira, GitHub
4. ✅ **Monitor usage** - Check search queries and refine
5. ✅ **Optimize** - Adjust min_score threshold based on feedback

---

## Support Commands

### Check System Status

```bash
# API server
curl http://localhost:8001/health

# Search API
curl http://localhost:8001/api/v1/search/stats

# Slack bot
curl http://localhost:8001/api/v1/slack/health

# Celery workers
celery -A src.workers.celery_app inspect active

# Database
docker compose ps
```

### View Logs

```bash
# API logs
tail -f logs/api.log

# Celery logs
tail -f logs/celery.log

# Docker logs
docker compose logs -f
```

### Restart Services

```bash
# API server
# Ctrl+C to stop, then:
uvicorn src.main:app --reload --port 8001

# Celery worker
celery -A src.workers.celery_app worker --loglevel=info

# All Docker services
docker compose restart
```

Happy searching! 🚀
