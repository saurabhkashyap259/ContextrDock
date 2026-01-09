#!/usr/bin/env python3
"""Test Confluence connector manually.

Quick test to verify Confluence API connectivity and data fetching.
"""

import os
import sys

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.connectors.confluence.connector import ConfluenceConnector
from src.connectors.sdk import OAuth2Token
from src.models.connector import Connector


def test_confluence_connection():
    """Test basic Confluence API connectivity."""
    
    # Get credentials from environment
    instance_url = os.getenv("CONFLUENCE_INSTANCE_URL", "https://yourcompany.atlassian.net")
    access_token = os.getenv("CONFLUENCE_ACCESS_TOKEN", "")
    api_token = os.getenv("CONFLUENCE_API_TOKEN", "")
    email = os.getenv("CONFLUENCE_EMAIL", "")
    
    # Handle API token (easier option)
    if api_token and email:
        import base64
        credentials = f"{email}:{api_token}"
        access_token = base64.b64encode(credentials.encode()).decode()
        print(f"✅ Using API Token authentication for {email}")
    elif api_token:
        print("⚠️  API token provided but missing email. Set CONFLUENCE_EMAIL environment variable.")
        print("   Or provide CONFLUENCE_ACCESS_TOKEN directly (OAuth or pre-encoded token)")
    
    if not access_token or access_token == "":
        print("❌ Error: No authentication credentials provided\n")
        print("=" * 60)
        print("OPTION 1: API Token (Recommended - Easiest!)")
        print("=" * 60)
        print("1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens")
        print("2. Click 'Create API token'")
        print("3. Copy the token")
        print("4. Set environment variables:\n")
        print("   export CONFLUENCE_INSTANCE_URL='https://yourcompany.atlassian.net'")
        print("   export CONFLUENCE_EMAIL='your.email@company.com'")
        print("   export CONFLUENCE_API_TOKEN='your_api_token_here'")
        print("\n" + "=" * 60)
        print("OPTION 2: OAuth Token (More Complex)")
        print("=" * 60)
        print("1. Go to: https://developer.atlassian.com/console/myapps/")
        print("2. Create OAuth 2.0 (3LO) app")
        print("3. Add scopes: read:confluence-content.all, read:confluence-space.summary")
        print("4. Get access token via OAuth flow")
        print("5. Set environment variables:\n")
        print("   export CONFLUENCE_INSTANCE_URL='https://yourcompany.atlassian.net'")
        print("   export CONFLUENCE_ACCESS_TOKEN='your_oauth_access_token'")
        print("\n⚡ TIP: Use API Token - it's much simpler and doesn't expire!")
        return False
    
    print(f"Testing Confluence connection to: {instance_url}")
    print("-" * 60)
    
    # Create mock connector object (not persisted to DB)
    class MockConnector:
        def __init__(self):
            self.id = 999
            self.workspace_id = 1
            self.name = "Test Confluence"
            self.config_json = {"instance_url": instance_url}
            self.credentials = {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
            }
    
    connector = MockConnector()
    
    try:
        # Initialize connector (pass None for db_session since we're just testing API)
        conf_connector = ConfluenceConnector(connector)
        conf_connector.db_session = None  # Override to avoid DB operations
        
        # Test 1: Fetch spaces
        print("\n1️⃣  Testing spaces API...")
        spaces_data = conf_connector._fetch_spaces_page(limit=5)
        spaces = spaces_data.get("results", [])
        
        print(f"✅ Found {len(spaces)} spaces:")
        for space in spaces[:5]:
            space_key = space.get("key")
            space_name = space.get("name")
            space_type = space.get("type")
            print(f"   • {space_key}: {space_name} ({space_type})")
        
        if not spaces:
            print("⚠️  No spaces found. Make sure your token has access to Confluence spaces.")
            return False
        
        # Test 2: Fetch pages
        print("\n2️⃣  Testing content API...")
        first_space = spaces[0]
        space_key = first_space.get("key")
        
        pages_data = conf_connector._fetch_pages_page(space_key=space_key, limit=5)
        pages = pages_data.get("results", [])
        
        print(f"✅ Found {len(pages)} pages in space '{space_key}':")
        for page in pages[:5]:
            page_id = page.get("id")
            page_title = page.get("title")
            page_type = page.get("type")
            print(f"   • {page_id}: {page_title} ({page_type})")
        
        if not pages:
            print(f"⚠️  No pages found in space {space_key}. Try another space or create some pages.")
            return False
        
        # Test 3: Fetch page details
        print("\n3️⃣  Testing page details...")
        first_page = pages[0]
        page_id = first_page.get("id")
        page_title = first_page.get("title")
        
        print(f"✅ Page: {page_title} (ID: {page_id})")
        
        # Get page body
        body = first_page.get("body", {})
        storage = body.get("storage", {})
        content_html = storage.get("value", "")
        
        if content_html:
            import re
            text_content = re.sub(r'<[^>]+>', ' ', content_html)
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            preview = text_content[:200] + "..." if len(text_content) > 200 else text_content
            print(f"   Content preview: {preview}")
        else:
            print("   (No content)")
        
        # Test 4: Load caches
        print("\n4️⃣  Testing cache loading...")
        conf_connector._load_spaces_cache()
        print(f"✅ Loaded {len(conf_connector._spaces_cache)} spaces into cache")
        
        # Test 5: Sync test (fetch a few documents)
        print("\n5️⃣  Testing sync (fetching first 3 pages)...")
        doc_count = 0
        for doc in conf_connector.sync(max_pages=3):
            doc_count += 1
            metadata = doc.get("metadata", {})
            title = metadata.get("page_title", "Untitled")
            space = metadata.get("space_key", "")
            print(f"   ✅ Document {doc_count}: {title} (space: {space})")
        
        print(f"\n✅ Sync test complete: {doc_count} documents")
        
        # Summary
        print("\n" + "=" * 60)
        print("✅ All Confluence connector tests passed!")
        print("=" * 60)
        print(f"\nYour Confluence instance: {instance_url}")
        print(f"Spaces available: {len(conf_connector._spaces_cache)}")
        print("\nNext steps:")
        print("1. Run: python setup_confluence.py setup \\")
        print(f"     --instance-url {instance_url} \\")
        print("     --access-token $CONFLUENCE_ACCESS_TOKEN \\")
        print("     --workspace-id 1")
        print("\n2. Run: python setup_confluence.py sync --connector-id <id>")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_confluence_connection()
    sys.exit(0 if success else 1)
