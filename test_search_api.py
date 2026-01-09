"""
Test Search API Endpoint

This script demonstrates how to use the ContextDock search API endpoint.
It shows various query patterns, filtering options, and pagination.

Usage:
    python test_search_api.py
"""

import json
import sys
from typing import Dict, Optional

import requests


API_BASE_URL = "http://localhost:8001/api/v1"


def search(
    query: str,
    limit: int = 5,
    offset: int = 0,
    channel_id: Optional[str] = None,
    source_type: Optional[str] = None,
    min_score: float = 0.0,
) -> Dict:
    """
    Perform semantic search via API.
    
    Args:
        query: Natural language search query
        limit: Maximum number of results
        offset: Pagination offset
        channel_id: Optional Slack channel filter
        source_type: Optional source type filter
        min_score: Minimum relevance score
        
    Returns:
        Search response dictionary
    """
    url = f"{API_BASE_URL}/search"
    
    payload = {
        "query": query,
        "limit": limit,
        "offset": offset,
        "min_score": min_score,
    }
    
    if channel_id:
        payload["channel_id"] = channel_id
    
    if source_type:
        payload["source_type"] = source_type
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}")
        sys.exit(1)


def get_stats() -> Dict:
    """Get search index statistics."""
    url = f"{API_BASE_URL}/search/stats"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}")
        sys.exit(1)


def check_health() -> Dict:
    """Check search service health."""
    url = f"{API_BASE_URL}/search/health"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}")
        sys.exit(1)


def display_results(response: Dict):
    """Display search results in a readable format."""
    print(f"\n🔍 Query: '{response['query']}'")
    print(f"📊 Found {response['total']} results (showing {len(response['results'])})")
    print(f"⏱️  Took: {response['took_ms']:.2f}ms")
    print(f"{'='*80}\n")
    
    for i, result in enumerate(response["results"], 1):
        print(f"Result {i}:")
        print(f"  Score: {result['score']:.4f}")
        print(f"  Title: {result['title'][:100]}...")
        print(f"  Channel: #{result['metadata']['channel_name']}")
        print(f"  User: {result['metadata']['username']}")
        if result['url']:
            print(f"  Link: {result['url']}")
        print()


def run_demo():
    """Run demonstration of search API features."""
    print("\n" + "="*80)
    print("🚀 ContextDock Search API Demo")
    print("="*80)
    
    # Check health
    print("\n1️⃣  Checking service health...")
    health = check_health()
    print(f"   Status: {health['status']}")
    print(f"   OpenAI: {health['openai']}")
    print(f"   Qdrant: {health['qdrant']}")
    
    # Get stats
    print("\n2️⃣  Fetching index statistics...")
    stats = get_stats()
    print(f"   Total documents: {stats['total_documents']}")
    print(f"   Total chunks: {stats['total_chunks']}")
    print(f"   Vector dimensions: {stats['vector_dimensions']}")
    print(f"   Sources: {stats['sources']}")
    
    # Test 1: Basic search
    print("\n3️⃣  Test: Basic semantic search")
    response = search("user engagement strategies", limit=3)
    display_results(response)
    
    # Test 2: Search with min_score filter
    print("\n4️⃣  Test: Search with relevance threshold")
    response = search(
        "ContextDock AI assistant",
        limit=2,
        min_score=0.5,
    )
    display_results(response)
    
    # Test 3: Pagination
    print("\n5️⃣  Test: Pagination (offset=2, limit=2)")
    response = search(
        "app features",
        limit=2,
        offset=2,
    )
    display_results(response)
    
    # Test 4: Channel filter
    print("\n6️⃣  Test: Channel-specific search")
    response = search(
        "ideas",
        limit=3,
        channel_id="CGREG0X9A",
    )
    display_results(response)
    
    print("\n" + "="*80)
    print("✅ Demo completed successfully!")
    print("="*80 + "\n")


def interactive_mode():
    """Run interactive search mode."""
    print("\n" + "="*80)
    print("🔍 ContextDock Search API - Interactive Mode")
    print("="*80)
    print("\nEnter search queries (or 'quit' to exit)")
    print()
    
    while True:
        try:
            query = input("\n🔎 Search: ").strip()
            
            if not query:
                continue
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            response = search(query, limit=5)
            display_results(response)
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test ContextDock Search API"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run full demo of API features",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive search mode",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Search query (if not using --demo or --interactive)",
    )
    
    args = parser.parse_args()
    
    # Check if API is accessible
    try:
        requests.get(f"{API_BASE_URL}/search/health", timeout=5)
    except requests.exceptions.RequestException:
        print(f"❌ Error: Cannot connect to API at {API_BASE_URL}")
        print("   Make sure the server is running: uvicorn src.main:app --reload --port 8001")
        sys.exit(1)
    
    # Run appropriate mode
    if args.demo:
        run_demo()
    elif args.interactive:
        interactive_mode()
    elif args.query:
        query = " ".join(args.query)
        response = search(query, limit=5)
        display_results(response)
    else:
        # Default to demo if no arguments
        run_demo()
