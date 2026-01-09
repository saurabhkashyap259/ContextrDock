"""
Test Semantic Search

This script tests semantic search functionality over indexed Slack messages.
It demonstrates:
1. Query embedding generation
2. Qdrant similarity search
3. Result ranking and formatting
4. Context retrieval

Usage:
    python test_semantic_search.py "user engagement ideas"
    python test_semantic_search.py "sleep tracking proposals"
"""

import argparse
import sys
from typing import List, Dict

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from src.config.settings import Settings

# Initialize settings
settings = Settings()

# Initialize clients
openai_client = openai.OpenAI(api_key=settings.openai_api_key)
qdrant_client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

COLLECTION_NAME = "contextdock"
EMBEDDING_MODEL = "text-embedding-3-small"


def generate_query_embedding(query: str) -> List[float]:
    """
    Generate embedding for search query.
    
    Args:
        query: Search query text
        
    Returns:
        Embedding vector
    """
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
    )
    return response.data[0].embedding


def search_messages(
    query: str,
    limit: int = 10,
    channel_id: str = None,
    workspace_id: int = 1,
) -> List[Dict]:
    """
    Perform semantic search on indexed messages.
    
    Args:
        query: Natural language search query
        limit: Maximum number of results
        channel_id: Optional channel filter
        workspace_id: Workspace ID filter
        
    Returns:
        List of matching messages with metadata and scores
    """
    print(f"\n🔍 Searching for: '{query}'")
    print(f"{'='*80}\n")
    
    # Generate query embedding
    print("📊 Generating query embedding...")
    query_embedding = generate_query_embedding(query)
    
    # Build filter
    filter_conditions = []
    
    # Always filter by workspace
    filter_conditions.append(
        FieldCondition(
            key="workspace_id",
            match=MatchValue(value=workspace_id),
        )
    )
    
    # Optional channel filter
    if channel_id:
        filter_conditions.append(
            FieldCondition(
                key="channel_id",
                match=MatchValue(value=channel_id),
            )
        )
    
    query_filter = Filter(must=filter_conditions) if filter_conditions else None
    
    # Perform search
    print(f"🔎 Searching Qdrant (top {limit} results)...")
    results = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
    
    print(f"✅ Found {len(results)} results\n")
    
    return results


def display_results(results: List, show_content: bool = True):
    """
    Display search results in a readable format.
    
    Args:
        results: List of Qdrant search results
        show_content: Whether to show full message content
    """
    if not results:
        print("❌ No results found")
        return
    
    print(f"📋 Top {len(results)} Results:")
    print(f"{'='*80}\n")
    
    for i, result in enumerate(results, 1):
        payload = result.payload
        score = result.score
        
        # Extract metadata
        channel = payload.get("channel_name", "unknown")
        username = payload.get("username", "Unknown User")
        title = payload.get("title", "")
        url = payload.get("url", "")
        content = payload.get("content", "")
        
        # Display result
        print(f"Result {i}:")
        print(f"  📊 Relevance Score: {score:.4f}")
        print(f"  📺 Channel: #{channel}")
        print(f"  👤 User: {username}")
        print(f"  📝 Title: {title[:100]}{'...' if len(title) > 100 else ''}")
        
        if url:
            print(f"  🔗 Link: {url}")
        
        if show_content:
            # Show first 300 chars of content
            content_preview = content[:300]
            if len(content) > 300:
                content_preview += "..."
            print(f"  💬 Content Preview:")
            print(f"     {content_preview}")
        
        print()


def interactive_mode():
    """Run interactive search mode."""
    print("\n" + "="*80)
    print("🔍 ContextDock Semantic Search - Interactive Mode")
    print("="*80)
    print("\nEnter search queries (or 'quit' to exit)")
    print("Examples:")
    print("  - user engagement ideas")
    print("  - sleep tracking proposals")
    print("  - app feature requests")
    print("  - ContextDock implementation")
    print()
    
    while True:
        try:
            query = input("\n🔎 Search: ").strip()
            
            if not query:
                continue
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            results = search_messages(query, limit=5)
            display_results(results, show_content=True)
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test semantic search over indexed Slack messages"
    )
    parser.add_argument(
        "query",
        type=str,
        nargs="*",
        help="Search query (use interactive mode if not provided)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results (default: 10)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        help="Filter by channel ID",
    )
    parser.add_argument(
        "--no-content",
        action="store_true",
        help="Don't show message content in results",
    )
    
    args = parser.parse_args()
    
    # Interactive mode if no query provided
    if not args.query:
        interactive_mode()
        return
    
    # Single query mode
    query = " ".join(args.query)
    results = search_messages(
        query=query,
        limit=args.limit,
        channel_id=args.channel,
    )
    display_results(results, show_content=not args.no_content)


if __name__ == "__main__":
    main()
