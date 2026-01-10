#!/usr/bin/env python3
"""Setup JIRA connector for ContextDock.

Creates connector record with credentials in the database.
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(__file__))

from src.models.connector import Connector
from src.database import SessionLocal

load_dotenv()


def setup_jira_connector():
    """Create JIRA connector in database."""
    
    # Get configuration from environment
    jira_url = os.getenv("JIRA_URL")
    jira_email = os.getenv("JIRA_EMAIL")
    jira_api_token = os.getenv("JIRA_API_TOKEN")
    jira_projects = os.getenv("JIRA_PROJECTS", "").split(",") if os.getenv("JIRA_PROJECTS") else []
    jira_jql_filter = os.getenv("JIRA_JQL_FILTER", "")
    
    # Validate required fields
    if not jira_url:
        print("❌ Error: JIRA_URL not set in .env")
        print("   Example: JIRA_URL=https://yourcompany.atlassian.net")
        sys.exit(1)
    
    if not jira_email:
        print("❌ Error: JIRA_EMAIL not set in .env")
        print("   Example: JIRA_EMAIL=your-email@company.com")
        sys.exit(1)
    
    if not jira_api_token:
        print("❌ Error: JIRA_API_TOKEN not set in .env")
        print("   Get token from: https://id.atlassian.com/manage-profile/security/api-tokens")
        sys.exit(1)
    
    # Clean up URL
    jira_url = jira_url.rstrip("/")
    
    print("🎫 Setting up JIRA connector...")
    print(f"   URL: {jira_url}")
    print(f"   Email: {jira_email}")
    
    if jira_projects:
        print(f"   Projects: {', '.join(jira_projects)}")
    
    if jira_jql_filter:
        print(f"   JQL Filter: {jira_jql_filter}")
    
    # Create connector
    db = SessionLocal()
    
    try:
        # Check if connector already exists
        existing = db.query(Connector).filter(
            Connector.connector_type == "jira",
            Connector.workspace_id == 1
        ).first()
        
        if existing:
            print(f"\n⚠️  JIRA connector already exists (ID: {existing.id})")
            response = input("   Update existing connector? (y/n): ")
            
            if response.lower() != 'y':
                print("   Cancelled.")
                return
            
            # Update existing
            existing.name = f"JIRA - {jira_url.split('//')[1]}"
            existing.config_json = {
                "instance_url": jira_url,
                "projects": jira_projects,
                "jql_filter": jira_jql_filter
            }
            existing.credentials_encrypted = {
                "email": jira_email,
                "api_token": jira_api_token
            }
            existing.is_active = True
            
            db.commit()
            print(f"✅ Updated JIRA connector (ID: {existing.id})")
            connector_id = existing.id
        else:
            # Create new
            connector = Connector(
                workspace_id=1,
                connector_type="jira",
                name=f"JIRA - {jira_url.split('//')[1]}",
                config_json={
                    "instance_url": jira_url,
                    "projects": jira_projects,
                    "jql_filter": jira_jql_filter
                },
                credentials_encrypted={
                    "email": jira_email,
                    "api_token": jira_api_token
                },
                is_active=True
            )
            
            db.add(connector)
            db.commit()
            print(f"✅ Created JIRA connector (ID: {connector.id})")
            connector_id = connector.id
        
        print("\n🎉 JIRA connector setup complete!")
        print(f"\n📋 Next steps:")
        print(f"   1. Run sync: python sync_jira_issues.py")
        print(f"   2. Check data: SELECT COUNT(*) FROM documents WHERE source_type='jira';")
        print(f"   3. Test search via Slack bot")
        
    except Exception as e:
        print(f"\n❌ Error setting up connector: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    setup_jira_connector()
