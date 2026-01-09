"""
Slack Message Sync Pipeline

This script fetches messages from Slack channels and indexes them for semantic search:
1. Fetches all messages from specified Slack channels (with pagination)
2. Stores messages in PostgreSQL as Document records
3. Generates embeddings using OpenAI text-embedding-3-small
4. Indexes embeddings in Qdrant vector database
5. Tracks progress and handles errors gracefully

Usage:
    python sync_slack_messages.py --channel CGREG0X9A  # Sync #ideas channel
    python sync_slack_messages.py --all                 # Sync all channels bot is in
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.config.settings import Settings
from src.models.document import Document
from src.models.document_chunk import DocumentChunk

# Initialize settings
settings = Settings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize clients
slack_client = WebClient(token=settings.slack_bot_token)
openai_client = openai.OpenAI(api_key=settings.openai_api_key)
qdrant_client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)

# Collection name in Qdrant
COLLECTION_NAME = "contextdock"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def ensure_qdrant_collection():
    """Ensure Qdrant collection exists with correct configuration."""
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
            logger.info(f"✅ Created collection: {COLLECTION_NAME}")
        else:
            logger.info(f"✅ Collection already exists: {COLLECTION_NAME}")
    except Exception as e:
        logger.error(f"❌ Error ensuring collection: {e}")
        raise


def get_channel_info(channel_id: str) -> Optional[Dict]:
    """Get channel information from Slack."""
    try:
        response = slack_client.conversations_info(channel=channel_id)
        return response["channel"]
    except SlackApiError as e:
        logger.error(f"❌ Error getting channel info: {e.response['error']}")
        return None


def fetch_all_messages(channel_id: str) -> List[Dict]:
    """
    Fetch all messages from a Slack channel with pagination.
    
    Args:
        channel_id: Slack channel ID
        
    Returns:
        List of message dictionaries
    """
    all_messages = []
    cursor = None
    
    logger.info(f"📬 Fetching messages from channel {channel_id}...")
    
    try:
        while True:
            # Fetch batch of messages
            response = slack_client.conversations_history(
                channel=channel_id,
                limit=200,  # Max per request
                cursor=cursor,
            )
            
            messages = response["messages"]
            all_messages.extend(messages)
            
            logger.info(f"   Fetched {len(messages)} messages (total: {len(all_messages)})")
            
            # Check if there are more messages
            if not response.get("has_more"):
                break
                
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
                
    except SlackApiError as e:
        error_code = e.response["error"]
        if error_code == "not_in_channel":
            logger.error(f"❌ Bot is not in channel {channel_id}. Please invite the bot first.")
        else:
            logger.error(f"❌ Slack API error: {error_code}")
        raise
    
    logger.info(f"✅ Fetched total of {len(all_messages)} messages")
    return all_messages


def get_user_info(user_id: str) -> Optional[Dict]:
    """Get user information from Slack (with basic caching)."""
    cache_key = f"user_{user_id}"
    
    # Simple in-memory cache
    if not hasattr(get_user_info, "cache"):
        get_user_info.cache = {}
    
    if cache_key in get_user_info.cache:
        return get_user_info.cache[cache_key]
    
    try:
        response = slack_client.users_info(user=user_id)
        user_info = response["user"]
        get_user_info.cache[cache_key] = user_info
        return user_info
    except SlackApiError as e:
        logger.warning(f"⚠️  Could not fetch user info for {user_id}: {e.response['error']}")
        return None


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def format_message_content(message: Dict, channel_info: Dict) -> str:
    """
    Format Slack message into readable text for embedding.
    
    Args:
        message: Slack message dictionary
        channel_info: Channel information dictionary
        
    Returns:
        Formatted message content
    """
    text = message.get("text", "")
    user_id = message.get("user", "Unknown")
    timestamp = message.get("ts", "")
    
    # Get user info
    user_info = get_user_info(user_id) if user_id != "Unknown" else None
    username = user_info.get("real_name", user_info.get("name", user_id)) if user_info else user_id
    
    # Format timestamp
    try:
        dt = datetime.fromtimestamp(float(timestamp))
        formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        formatted_time = timestamp
    
    # Build content
    channel_name = channel_info.get("name", "unknown")
    content_parts = [
        f"Channel: #{channel_name}",
        f"User: {username}",
        f"Date: {formatted_time}",
        f"Message: {text}",
    ]
    
    # Add thread info if it's a thread reply
    if message.get("thread_ts") and message.get("thread_ts") != timestamp:
        content_parts.insert(3, "Type: Thread Reply")
    
    # Add reactions if present
    reactions = message.get("reactions", [])
    if reactions:
        reaction_strs = [f"{r['name']}:{r['count']}" for r in reactions]
        content_parts.append(f"Reactions: {', '.join(reaction_strs)}")
    
    return "\n".join(content_parts)


def generate_embedding(text: str) -> List[float]:
    """
    Generate embedding for text using OpenAI.
    
    Args:
        text: Text to embed
        
    Returns:
        Embedding vector (1536 dimensions)
    """
    try:
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"❌ Error generating embedding: {e}")
        raise


def sync_message_to_database(
    message: Dict,
    channel_info: Dict,
    workspace_id: int,
    connector_id: int,
    db_session,
) -> Optional[Document]:
    """
    Sync a single message to the database.
    
    Args:
        message: Slack message dictionary
        channel_info: Channel information
        workspace_id: Workspace ID
        connector_id: Connector ID
        db_session: SQLAlchemy session
        
    Returns:
        Document object or None if skipped
    """
    # Skip non-message types (joins, leaves, etc.)
    msg_type = message.get("type")
    subtype = message.get("subtype")
    
    if msg_type != "message" or subtype in ["channel_join", "channel_leave"]:
        return None
    
    # Extract message data
    source_id = f"slack_{channel_info['id']}_{message['ts']}"
    text = message.get("text", "")
    
    # Skip empty messages
    if not text.strip():
        return None
    
    # Format content
    content = format_message_content(message, channel_info)
    content_hash = compute_content_hash(content)
    
    # Build message URL
    team_id = message.get("team")
    channel_id = channel_info["id"]
    ts = message["ts"].replace(".", "")
    url = f"https://slack.com/archives/{channel_id}/p{ts}"
    
    # Build metadata
    user_id = message.get("user", "Unknown")
    user_info = get_user_info(user_id) if user_id != "Unknown" else None
    
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
    
    # Check if document already exists
    existing = db_session.query(Document).filter_by(
        source_type="slack",
        source_id=source_id,
    ).first()
    
    if existing:
        # Check if content changed
        if existing.content_hash == content_hash:
            logger.debug(f"   Skipping unchanged message: {source_id}")
            return existing
        
        # Update existing document
        logger.info(f"   Updating changed message: {source_id}")
        existing.title = text[:1000]  # First 1000 chars as title
        existing.url = url
        existing.content_hash = content_hash
        existing.metadata_json = metadata
        existing.last_indexed_at = datetime.utcnow()
        existing.updated_at = datetime.utcnow()
        
        # Delete old chunks (will be recreated)
        db_session.query(DocumentChunk).filter_by(document_id=existing.id).delete()
        db_session.commit()
        
        return existing
    
    # Create new document
    document = Document(
        workspace_id=workspace_id,
        connector_id=connector_id,
        source_type="slack",
        source_id=source_id,
        title=text[:1000],  # First 1000 chars as title
        url=url,
        content_hash=content_hash,
        metadata_json=metadata,
    )
    
    db_session.add(document)
    db_session.commit()
    
    logger.debug(f"   Created document: {document.id} - {source_id}")
    
    return document


def index_document_to_qdrant(document: Document, content: str, db_session) -> bool:
    """
    Generate embedding and index document in Qdrant.
    
    Args:
        document: Document object from database
        content: Formatted message content
        db_session: SQLAlchemy session
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Generate embedding
        logger.debug(f"   Generating embedding for document {document.id}...")
        embedding = generate_embedding(content)
        
        # Create point ID (must be integer for Qdrant)
        point_id = document.id
        
        # Prepare metadata for Qdrant
        payload = {
            "document_id": document.id,
            "workspace_id": document.workspace_id,
            "source_type": document.source_type,
            "source_id": document.source_id,
            "title": document.title,
            "url": document.url,
            "channel_id": document.metadata_json.get("channel_id"),
            "channel_name": document.metadata_json.get("channel_name"),
            "user_id": document.metadata_json.get("user_id"),
            "username": document.metadata_json.get("username"),
            "message_ts": document.metadata_json.get("message_ts"),
            "content": content,
        }
        
        # Index in Qdrant
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload=payload,
        )
        
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point],
        )
        
        # Create DocumentChunk record
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=0,  # Slack messages are single chunks
            content=content,
            token_count=len(content.split()),  # Rough token count
            embedding_id=point_id,
            acl_json={
                "channel_id": document.metadata_json.get("channel_id"),
                "visibility": "workspace",  # All workspace members can see
            },
        )
        
        db_session.add(chunk)
        db_session.commit()
        
        logger.debug(f"   ✅ Indexed document {document.id} in Qdrant")
        return True
        
    except Exception as e:
        logger.error(f"   ❌ Error indexing document {document.id}: {e}")
        return False


def sync_channel(channel_id: str, workspace_id: int = 1, connector_id: int = 1):
    """
    Sync all messages from a Slack channel.
    
    Args:
        channel_id: Slack channel ID
        workspace_id: Workspace ID (default: 1)
        connector_id: Connector ID (default: 1)
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"🚀 Starting sync for channel: {channel_id}")
    logger.info(f"{'='*80}\n")
    
    # Ensure Qdrant collection exists
    ensure_qdrant_collection()
    
    # Get channel info
    channel_info = get_channel_info(channel_id)
    if not channel_info:
        logger.error(f"❌ Could not get channel info for {channel_id}")
        return
    
    channel_name = channel_info.get("name", "unknown")
    logger.info(f"📺 Channel: #{channel_name} ({channel_id})")
    
    # Fetch all messages
    try:
        messages = fetch_all_messages(channel_id)
    except Exception as e:
        logger.error(f"❌ Failed to fetch messages: {e}")
        return
    
    if not messages:
        logger.warning(f"⚠️  No messages found in #{channel_name}")
        return
    
    # Process messages
    logger.info(f"\n💾 Processing {len(messages)} messages...")
    
    db_session = SessionLocal()
    
    try:
        created_count = 0
        updated_count = 0
        skipped_count = 0
        indexed_count = 0
        error_count = 0
        
        for i, message in enumerate(messages, 1):
            if i % 10 == 0:
                logger.info(f"   Progress: {i}/{len(messages)} messages...")
            
            # Sync to database
            document = sync_message_to_database(
                message=message,
                channel_info=channel_info,
                workspace_id=workspace_id,
                connector_id=connector_id,
                db_session=db_session,
            )
            
            if not document:
                skipped_count += 1
                continue
            
            # Track if new or updated
            if document.created_at == document.updated_at:
                created_count += 1
            else:
                updated_count += 1
            
            # Index in Qdrant
            content = format_message_content(message, channel_info)
            success = index_document_to_qdrant(document, content, db_session)
            
            if success:
                indexed_count += 1
            else:
                error_count += 1
        
        # Summary
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ Sync completed for #{channel_name}!")
        logger.info(f"{'='*80}")
        logger.info(f"📊 Statistics:")
        logger.info(f"   Total messages: {len(messages)}")
        logger.info(f"   Created: {created_count}")
        logger.info(f"   Updated: {updated_count}")
        logger.info(f"   Skipped: {skipped_count}")
        logger.info(f"   Indexed: {indexed_count}")
        logger.info(f"   Errors: {error_count}")
        logger.info(f"{'='*80}\n")
        
    except Exception as e:
        logger.error(f"❌ Error during sync: {e}")
        db_session.rollback()
        raise
    finally:
        db_session.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Sync Slack messages to ContextDock")
    parser.add_argument(
        "--channel",
        type=str,
        help="Slack channel ID to sync (e.g., CGREG0X9A for #ideas)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Sync all channels the bot is in",
    )
    parser.add_argument(
        "--workspace-id",
        type=int,
        default=1,
        help="Workspace ID (default: 1)",
    )
    parser.add_argument(
        "--connector-id",
        type=int,
        default=1,
        help="Connector ID (default: 1)",
    )
    
    args = parser.parse_args()
    
    if not args.channel and not args.all:
        parser.error("Must specify either --channel or --all")
    
    # Sync specific channel
    if args.channel:
        sync_channel(
            channel_id=args.channel,
            workspace_id=args.workspace_id,
            connector_id=args.connector_id,
        )
    
    # Sync all channels
    if args.all:
        logger.info("🔍 Discovering channels bot is in...")
        try:
            response = slack_client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True,
            )
            
            # Filter to channels bot is a member of
            channels = [
                ch for ch in response["channels"]
                if ch.get("is_member", False)
            ]
            
            logger.info(f"Found {len(channels)} channels to sync")
            
            for channel in channels:
                sync_channel(
                    channel_id=channel["id"],
                    workspace_id=args.workspace_id,
                    connector_id=args.connector_id,
                )
                
        except SlackApiError as e:
            logger.error(f"❌ Error listing channels: {e.response['error']}")
            sys.exit(1)


if __name__ == "__main__":
    main()
