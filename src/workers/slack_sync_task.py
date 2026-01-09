"""
Celery task for Slack message synchronization.

This task fetches messages from Slack channels and indexes them
for semantic search using the same pipeline as sync_slack_messages.py.
"""

import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.database import get_db
from src.models.connector import Connector
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.models.sync_run import SyncRun, SyncStatus
from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Initialize clients
openai_client = openai.OpenAI(api_key=settings.openai_api_key)
qdrant_client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

COLLECTION_NAME = "contextdock"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def ensure_qdrant_collection():
    """Ensure Qdrant collection exists."""
    try:
        collections = qdrant_client.get_collections().collections
        collection_names = [col.name for col in collections]
        
        if COLLECTION_NAME not in collection_names:
            logger.info(f"Creating Qdrant collection: {COLLECTION_NAME}")
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSIONS,
                    distance=Distance.COSINE,
                ),
            )
    except Exception as e:
        logger.error(f"Error ensuring Qdrant collection: {e}")
        raise


def get_user_info_cached(slack_client: WebClient, user_id: str, cache: dict) -> Optional[Dict]:
    """Get user info with caching."""
    if user_id in cache:
        return cache[user_id]
    
    try:
        response = slack_client.users_info(user=user_id)
        user_info = response["user"]
        cache[user_id] = user_info
        return user_info
    except SlackApiError as e:
        logger.warning(f"Could not fetch user info for {user_id}: {e.response['error']}")
        return None


def format_message_content(message: Dict, channel_info: Dict, user_cache: dict, slack_client: WebClient) -> str:
    """Format Slack message into readable text."""
    text = message.get("text", "")
    user_id = message.get("user", "Unknown")
    timestamp = message.get("ts", "")
    
    user_info = get_user_info_cached(slack_client, user_id, user_cache) if user_id != "Unknown" else None
    username = user_info.get("real_name", user_info.get("name", user_id)) if user_info else user_id
    
    try:
        dt = datetime.fromtimestamp(float(timestamp))
        formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        formatted_time = timestamp
    
    channel_name = channel_info.get("name", "unknown")
    content_parts = [
        f"Channel: #{channel_name}",
        f"User: {username}",
        f"Date: {formatted_time}",
        f"Message: {text}",
    ]
    
    if message.get("thread_ts") and message.get("thread_ts") != timestamp:
        content_parts.insert(3, "Type: Thread Reply")
    
    reactions = message.get("reactions", [])
    if reactions:
        reaction_strs = [f"{r['name']}:{r['count']}" for r in reactions]
        content_parts.append(f"Reactions: {', '.join(reaction_strs)}")
    
    return "\n".join(content_parts)


def generate_embedding(text: str) -> List[float]:
    """Generate embedding using OpenAI."""
    try:
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        raise


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@celery_app.task(name="sync_slack_channel", bind=True, max_retries=3)
def sync_slack_channel(
    self,
    connector_id: int,
    channel_id: str,
    workspace_id: int = 1,
) -> Dict:
    """
    Sync messages from a Slack channel.
    
    Args:
        connector_id: Connector ID
        channel_id: Slack channel ID
        workspace_id: Workspace ID
        
    Returns:
        Dict with sync statistics
    """
    logger.info(f"Starting Slack channel sync: channel={channel_id}, connector={connector_id}")
    
    db = next(get_db())
    stats = {
        "channel_id": channel_id,
        "fetched": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "indexed": 0,
        "errors": 0,
    }
    
    try:
        # Get connector
        connector = db.query(Connector).filter_by(id=connector_id).first()
        if not connector:
            raise ValueError(f"Connector {connector_id} not found")
        
        # Get Slack token from connector credentials
        bot_token = settings.slack_bot_token
        if not bot_token:
            raise ValueError("Slack bot token not configured")
        
        slack_client = WebClient(token=bot_token)
        
        # Ensure Qdrant collection
        ensure_qdrant_collection()
        
        # Get channel info
        try:
            channel_response = slack_client.conversations_info(channel=channel_id)
            channel_info = channel_response["channel"]
        except SlackApiError as e:
            logger.error(f"Failed to get channel info: {e.response['error']}")
            raise
        
        # Fetch messages with pagination
        user_cache = {}
        cursor = None
        
        while True:
            try:
                response = slack_client.conversations_history(
                    channel=channel_id,
                    limit=200,
                    cursor=cursor,
                )
                
                messages = response["messages"]
                stats["fetched"] += len(messages)
                
                # Process each message
                for message in messages:
                    try:
                        # Skip non-message types
                        msg_type = message.get("type")
                        subtype = message.get("subtype")
                        
                        if msg_type != "message" or subtype in ["channel_join", "channel_leave"]:
                            stats["skipped"] += 1
                            continue
                        
                        text = message.get("text", "")
                        if not text.strip():
                            stats["skipped"] += 1
                            continue
                        
                        # Format content
                        content = format_message_content(message, channel_info, user_cache, slack_client)
                        content_hash = compute_content_hash(content)
                        
                        # Build source ID
                        source_id = f"slack_{channel_id}_{message['ts']}"
                        
                        # Build URL
                        ts = message["ts"].replace(".", "")
                        url = f"https://slack.com/archives/{channel_id}/p{ts}"
                        
                        # Build metadata
                        user_id = message.get("user", "Unknown")
                        user_info = get_user_info_cached(slack_client, user_id, user_cache) if user_id != "Unknown" else None
                        
                        metadata = {
                            "channel_id": channel_id,
                            "channel_name": channel_info.get("name"),
                            "message_ts": message["ts"],
                            "user_id": user_id,
                            "username": user_info.get("real_name", user_info.get("name", user_id)) if user_info else user_id,
                            "thread_ts": message.get("thread_ts"),
                            "reactions": message.get("reactions", []),
                            "is_thread_reply": message.get("thread_ts") is not None and message.get("thread_ts") != message["ts"],
                        }
                        
                        # Check if document exists
                        existing = db.query(Document).filter_by(
                            source_type="slack",
                            source_id=source_id,
                        ).first()
                        
                        if existing:
                            if existing.content_hash == content_hash:
                                stats["skipped"] += 1
                                continue
                            
                            # Update existing
                            existing.title = text[:1000]
                            existing.url = url
                            existing.content_hash = content_hash
                            existing.metadata_json = metadata
                            existing.last_indexed_at = datetime.utcnow()
                            existing.updated_at = datetime.utcnow()
                            
                            db.query(DocumentChunk).filter_by(document_id=existing.id).delete()
                            db.commit()
                            
                            document = existing
                            stats["updated"] += 1
                        else:
                            # Create new document
                            document = Document(
                                workspace_id=workspace_id,
                                connector_id=connector_id,
                                source_type="slack",
                                source_id=source_id,
                                title=text[:1000],
                                url=url,
                                content_hash=content_hash,
                                metadata_json=metadata,
                            )
                            db.add(document)
                            db.commit()
                            stats["created"] += 1
                        
                        # Generate embedding and index
                        try:
                            embedding = generate_embedding(content)
                            
                            point = PointStruct(
                                id=document.id,
                                vector=embedding,
                                payload={
                                    "document_id": document.id,
                                    "workspace_id": document.workspace_id,
                                    "source_type": document.source_type,
                                    "source_id": document.source_id,
                                    "title": document.title,
                                    "url": document.url,
                                    "channel_id": metadata.get("channel_id"),
                                    "channel_name": metadata.get("channel_name"),
                                    "user_id": metadata.get("user_id"),
                                    "username": metadata.get("username"),
                                    "message_ts": metadata.get("message_ts"),
                                    "content": content,
                                },
                            )
                            
                            qdrant_client.upsert(
                                collection_name=COLLECTION_NAME,
                                points=[point],
                            )
                            
                            # Create chunk record
                            chunk = DocumentChunk(
                                document_id=document.id,
                                chunk_index=0,
                                content=content,
                                token_count=len(content.split()),
                                embedding_id=str(document.id),
                                acl_json={
                                    "channel_id": metadata.get("channel_id"),
                                    "visibility": "workspace",
                                },
                            )
                            db.add(chunk)
                            db.commit()
                            
                            stats["indexed"] += 1
                        except Exception as e:
                            logger.error(f"Error indexing document {document.id}: {e}")
                            stats["errors"] += 1
                    
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        stats["errors"] += 1
                
                # Check for more messages
                if not response.get("has_more"):
                    break
                
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            
            except SlackApiError as e:
                logger.error(f"Slack API error: {e.response['error']}")
                raise
        
        logger.info(
            f"Slack channel sync completed: {stats['created']} created, "
            f"{stats['updated']} updated, {stats['indexed']} indexed, "
            f"{stats['errors']} errors"
        )
        
        return stats
    
    except Exception as e:
        logger.error(f"Slack channel sync failed: {e}")
        db.rollback()
        
        # Retry on failure
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        
        raise
    
    finally:
        db.close()


@celery_app.task(name="sync_slack_workspace", bind=True)
def sync_slack_workspace(self, connector_id: int, workspace_id: int = 1) -> Dict:
    """
    Sync all channels from a Slack workspace.
    
    Args:
        connector_id: Connector ID
        workspace_id: Workspace ID
        
    Returns:
        Dict with sync statistics
    """
    logger.info(f"Starting Slack workspace sync: connector={connector_id}")
    
    bot_token = settings.slack_bot_token
    if not bot_token:
        raise ValueError("Slack bot token not configured")
    
    slack_client = WebClient(token=bot_token)
    
    # Get all channels bot is member of
    try:
        response = slack_client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
        )
        
        channels = [
            ch for ch in response["channels"]
            if ch.get("is_member", False)
        ]
        
        logger.info(f"Found {len(channels)} channels to sync")
        
        # Sync each channel
        total_stats = {
            "channels": len(channels),
            "total_created": 0,
            "total_updated": 0,
            "total_indexed": 0,
            "total_errors": 0,
        }
        
        for channel in channels:
            try:
                stats = sync_slack_channel.apply_async(
                    args=(connector_id, channel["id"], workspace_id),
                    countdown=0,
                ).get(timeout=600)  # 10 minute timeout per channel
                
                total_stats["total_created"] += stats.get("created", 0)
                total_stats["total_updated"] += stats.get("updated", 0)
                total_stats["total_indexed"] += stats.get("indexed", 0)
                total_stats["total_errors"] += stats.get("errors", 0)
            
            except Exception as e:
                logger.error(f"Failed to sync channel {channel['id']}: {e}")
                total_stats["total_errors"] += 1
        
        logger.info(f"Slack workspace sync completed: {total_stats}")
        return total_stats
    
    except SlackApiError as e:
        logger.error(f"Failed to list channels: {e.response['error']}")
        raise
