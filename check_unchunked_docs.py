#!/usr/bin/env python3
"""Check documents without chunks and fetch their content size from Confluence."""

import sys
import os
import requests
from requests.auth import HTTPBasicAuth

sys.path.append(os.path.dirname(__file__))

from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.database import SessionLocal
from dotenv import load_dotenv

load_dotenv()

# Get Confluence credentials
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")

def get_page_content_size(page_id: str) -> int:
    """Fetch page from Confluence API and return content size."""
    try:
        url = f"{CONFLUENCE_URL}/wiki/api/v2/pages/{page_id}?body-format=storage"
        auth = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
        response = requests.get(url, auth=auth)
        
        if response.status_code == 200:
            data = response.json()
            html_content = data.get("body", {}).get("storage", {}).get("value", "")
            
            # Strip HTML tags for rough text size
            from html.parser import HTMLParser
            class HTMLStripper(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                def handle_data(self, data):
                    self.text.append(data)
                def get_text(self):
                    return ''.join(self.text)
            
            stripper = HTMLStripper()
            stripper.feed(html_content)
            text_content = stripper.get_text()
            
            return len(html_content), len(text_content)
        else:
            return 0, 0
    except Exception as e:
        return 0, 0


def main():
    db = SessionLocal()
    
    # Find documents without chunks
    documents_without_chunks = db.query(Document).outerjoin(DocumentChunk).filter(
        DocumentChunk.id == None,
        Document.source_type == 'confluence'
    ).all()
    
    print(f"\n📊 Analyzing {len(documents_without_chunks)} Confluence documents without chunks...\n")
    
    large_docs = []
    
    for i, doc in enumerate(documents_without_chunks, 1):
        # Extract page ID from source_id (format: confluence_PAGEID)
        page_id = doc.source_id.replace('confluence_', '')
        
        html_size, text_size = get_page_content_size(page_id)
        
        if text_size > 10000:  # More than 10KB of text
            large_docs.append((doc, html_size, text_size))
            print(f"⚠️  {doc.id:<6} {doc.title[:50]:<52} HTML: {html_size:>8} Text: {text_size:>8}")
        elif i <= 20:  # Show first 20 regardless
            status = "✅" if text_size < 1000 else "⚠️"
            print(f"{status}  {doc.id:<6} {doc.title[:50]:<52} HTML: {html_size:>8} Text: {text_size:>8}")
        
        if i % 10 == 0:
            print(f"   ... processed {i}/{len(documents_without_chunks)}")
    
    print("\n" + "="*100)
    print(f"\n🔍 Summary:")
    print(f"   Total documents without chunks: {len(documents_without_chunks)}")
    print(f"   Large documents (>10KB text): {len(large_docs)}")
    
    if large_docs:
        print(f"\n📋 Large documents that likely failed to chunk:")
        print(f"   {'ID':<6} {'Title':<50} {'Text Size':<12}")
        print("   " + "-"*70)
        for doc, html_size, text_size in sorted(large_docs, key=lambda x: x[2], reverse=True):
            print(f"   {doc.id:<6} {doc.title[:47]:<50} {text_size:>10} bytes")
    
    db.close()


if __name__ == "__main__":
    main()
