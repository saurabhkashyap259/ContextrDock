#!/usr/bin/env python3
"""
Test script for Slack bot search integration.
Tests the search_contextdock() function and result formatting.
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from integrations.slack_bot import search_contextdock, format_search_results


def test_search_integration():
    """Test the search integration function."""
    print("=" * 80)
    print("Testing Slack Bot Search Integration")
    print("=" * 80)
    print()
    
    # Test 1: Basic search
    print("Test 1: Basic Search")
    print("-" * 80)
    try:
        query = "user engagement ideas"
        print(f"Query: {query}")
        results = search_contextdock(query, limit=3, min_score=0.3)
        
        print(f"✅ Search successful!")
        print(f"   Total results: {results.get('total', 0)}")
        print(f"   Returned: {len(results.get('results', []))}")
        print(f"   Time: {results.get('took_ms', 0)}ms")
        print()
        
        # Show first result
        if results.get('results'):
            first = results['results'][0]
            print(f"   Top result:")
            print(f"   - Title: {first.get('title', 'N/A')}")
            print(f"   - Score: {first.get('score', 0):.4f}")
            print(f"   - Content preview: {first.get('content', '')[:100]}...")
            print()
    except Exception as e:
        print(f"❌ Search failed: {e}")
        print()
        return False
    
    # Test 2: Format results
    print("Test 2: Format Results as Slack Blocks")
    print("-" * 80)
    try:
        blocks = format_search_results(results, query)
        print(f"✅ Formatting successful!")
        print(f"   Total blocks: {len(blocks)}")
        print(f"   Block types: {[b.get('type') for b in blocks[:5]]}")
        print()
        
        # Show header block
        header = next((b for b in blocks if b.get('type') == 'header'), None)
        if header:
            print(f"   Header: {header['text']['text']}")
            print()
    except Exception as e:
        print(f"❌ Formatting failed: {e}")
        print()
        return False
    
    # Test 3: Empty query handling
    print("Test 3: Empty Results Handling")
    print("-" * 80)
    try:
        empty_results = {"total": 0, "results": [], "took_ms": 50}
        blocks = format_search_results(empty_results, "nonexistent query")
        
        has_no_results_msg = any(
            "No results found" in str(b.get('text', {}).get('text', ''))
            for b in blocks
        )
        
        if has_no_results_msg:
            print("✅ Empty results handled correctly!")
            print("   Shows 'No results found' message")
        else:
            print("⚠️  No results message not found in blocks")
        print()
    except Exception as e:
        print(f"❌ Empty results handling failed: {e}")
        print()
        return False
    
    # Test 4: Search with filters
    print("Test 4: Search with Filters")
    print("-" * 80)
    try:
        query = "ContextDock"
        results = search_contextdock(query, limit=2, min_score=0.4)
        
        print(f"✅ Filtered search successful!")
        print(f"   Query: {query}")
        print(f"   Min score: 0.4")
        print(f"   Total results: {results.get('total', 0)}")
        print(f"   Returned: {len(results.get('results', []))}")
        print()
        
        # Verify all results meet min_score
        if results.get('results'):
            scores = [r.get('score', 0) for r in results['results']]
            min_actual = min(scores)
            print(f"   Lowest score: {min_actual:.4f}")
            if min_actual >= 0.4:
                print(f"   ✅ All results meet min_score threshold")
            else:
                print(f"   ⚠️  Some results below threshold")
        print()
    except Exception as e:
        print(f"❌ Filtered search failed: {e}")
        print()
        return False
    
    print("=" * 80)
    print("✅ All tests passed!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Get your Slack Signing Secret from https://api.slack.com/apps")
    print("2. Add it to .env: SLACK_SIGNING_SECRET=your_secret_here")
    print("3. Restart API server: uvicorn src.main:app --reload --port 8001")
    print("4. Follow docs/slack-bot-setup.md for complete configuration")
    print()
    
    return True


if __name__ == "__main__":
    success = test_search_integration()
    sys.exit(0 if success else 1)
