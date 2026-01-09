"""API routes for Slack bot integration."""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response, status

from src.api.schemas.search import SearchRequest
from src.config.settings import Settings
from src.integrations.slack_bot import (
    format_search_results,
    handle_app_mention,
    handle_direct_message,
    handle_slash_command,
    search_contextdock,
)

logger = logging.getLogger(__name__)
settings = Settings()

router = APIRouter(prefix="/v1/slack", tags=["slack"])


def verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """
    Verify Slack request signature.
    
    Args:
        body: Raw request body
        timestamp: X-Slack-Request-Timestamp header
        signature: X-Slack-Signature header
        
    Returns:
        True if signature is valid
    """
    if not settings.slack_signing_secret:
        logger.warning("Slack signing secret not configured - skipping verification")
        return True
    
    # Prevent replay attacks - reject requests older than 5 minutes
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    
    # Compute signature
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    my_signature = 'v0=' + hmac.new(
        settings.slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(my_signature, signature)


@router.post("/events", status_code=status.HTTP_200_OK)
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_request_timestamp: str = Header(None),
    x_slack_signature: str = Header(None),
):
    """
    Handle Slack Events API requests.
    
    Receives events for:
    - app_mention: When bot is @mentioned
    - message.im: When bot receives a DM
    
    Setup:
    1. Go to https://api.slack.com/apps → Your App → Event Subscriptions
    2. Enable Events: ON
    3. Request URL: https://your-domain.com/api/v1/slack/events
    4. Subscribe to bot events:
       - app_mention
       - message.im
    5. Save Changes and reinstall app
    
    Args:
        request: FastAPI request object
        x_slack_request_timestamp: Request timestamp header (optional for URL verification)
        x_slack_signature: Request signature header (optional for URL verification)
        
    Returns:
        200 OK with challenge or empty response
    """
    body = await request.body()
    
    # Parse JSON body first
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON",
        )
    
    # Handle URL verification challenge (no signature verification needed)
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    
    # Verify request signature for all other events
    if not x_slack_request_timestamp or not x_slack_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required headers",
        )
    
    if not verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid request signature",
        )
    
    # Handle events in background to avoid blocking Slack's webhook timeout
    event_type = data.get("event", {}).get("type")
    event = data.get("event", {})
    
    logger.info(f"Received event: type={event_type}, subtype={event.get('subtype')}, bot_id={event.get('bot_id')}, user={event.get('user')}")
    
    if event_type == "app_mention":
        # Bot was @mentioned - run in background
        logger.info("Dispatching app_mention handler")
        background_tasks.add_task(handle_app_mention, event)
    elif event_type == "message":
        # Check if it's a DM (channel starts with 'D')
        channel_type = event.get("channel_type")
        if channel_type == "im":
            logger.info("Dispatching direct_message handler")
            background_tasks.add_task(handle_direct_message, event)
    
    # Return immediately to Slack (within 3 seconds requirement)
    return Response(status_code=status.HTTP_200_OK)


@router.post("/commands", status_code=status.HTTP_200_OK)
async def slack_slash_commands(
    request: Request,
    x_slack_request_timestamp: str = Header(...),
    x_slack_signature: str = Header(...),
):
    """
    Handle Slack slash commands.
    
    Usage: /contextdock search user engagement ideas
    
    Setup:
    1. Go to https://api.slack.com/apps → Your App → Slash Commands
    2. Create New Command:
       - Command: /contextdock
       - Request URL: https://your-domain.com/api/v1/slack/commands
       - Short Description: Search ContextDock knowledge base
       - Usage Hint: search <query>
    3. Save and reinstall app
    
    Args:
        request: FastAPI request object
        x_slack_request_timestamp: Request timestamp header
        x_slack_signature: Request signature header
        
    Returns:
        Slack message response
    """
    body = await request.body()
    
    # Verify request signature
    if not verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid request signature",
        )
    
    # Parse form data
    form_data = await request.form()
    command_data = {
        "command": form_data.get("command"),
        "text": form_data.get("text", ""),
        "user_id": form_data.get("user_id"),
        "channel_id": form_data.get("channel_id"),
        "team_id": form_data.get("team_id"),
    }
    
    # Handle command
    response = handle_slash_command(command_data)
    
    return response


@router.get("/health", status_code=status.HTTP_200_OK)
async def slack_bot_health():
    """
    Check Slack bot health.
    
    Returns:
        Health status
    """
    health = {
        "status": "unknown",
        "bot_token": "not_configured",
        "signing_secret": "not_configured",
    }
    
    if settings.slack_bot_token:
        health["bot_token"] = "configured"
    
    if settings.slack_signing_secret:
        health["signing_secret"] = "configured"
    
    if health["bot_token"] == "configured" and health["signing_secret"] == "configured":
        health["status"] = "ready"
    elif health["bot_token"] == "configured":
        health["status"] = "partial"
    else:
        health["status"] = "not_configured"
    
    return health
