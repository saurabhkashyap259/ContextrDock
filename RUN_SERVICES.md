# Running ContextDock Services

## Terminal 1: Ngrok (Expose Local Server)

```bash
cd /Users/saurabhkashyap/personal/ContextDock
ngrok http 8000
```

**After ngrok starts:**
- Copy the HTTPS forwarding URL (e.g., `https://abc123.ngrok.io`)
- Update Slack app's Event Subscriptions URL to: `https://abc123.ngrok.io/slack/events`

---

## Terminal 2: Slack Bot

```bash
cd /Users/saurabhkashyap/personal/ContextDock
source .venv/bin/activate
python src/integrations/slack_bot_main.py
```

**Expected output:**
```
Starting ContextDock Slack Bot...
Slack tokens verified
Connecting to Slack...
⚡️ Bolt app is running!
```

---

## Quick Start (All Commands)

### Terminal 1 - Ngrok
```bash
cd /Users/saurabhkashyap/personal/ContextDock && ngrok http 8000
```

### Terminal 2 - Slack Bot
```bash
cd /Users/saurabhkashyap/personal/ContextDock && source .venv/bin/activate && python src/integrations/slack_bot_main.py
```

---

## Troubleshooting

**Bot not responding?**
- Check ngrok is running and URL is updated in Slack app settings
- Verify `.env` has correct tokens (SLACK_BOT_TOKEN, SLACK_APP_TOKEN)
- Check bot is running without errors

**Ngrok URL changed?**
- Ngrok free tier provides new URL on each restart
- Update Slack Event Subscriptions URL with new ngrok URL
- Bot will automatically reconnect

---

## Optional: Run with tmux (Single Terminal, Multiple Panes)

```bash
# Start tmux session
tmux new -s contextdock

# Split terminal horizontally (Ctrl+B, then ")
# Terminal 1: ngrok http 8000

# Switch to second pane (Ctrl+B, then arrow key)
# Terminal 2: source .venv/bin/activate && python src/integrations/slack_bot_main.py

# Detach from tmux: Ctrl+B, then D
# Reattach later: tmux attach -t contextdock
```
