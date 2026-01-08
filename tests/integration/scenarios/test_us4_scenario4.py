"""US4 Scenario 4: Citations with Clickable Links

Tests citation formatting includes clickable deep links to sources.
"""

import pytest

from src.integrations.slack_formatter import SlackFormatter


class TestCitationFormatting:
    """Test citation formatting with links."""
    
    def test_citations_have_clickable_links(self):
        """Citations should have Slack-formatted clickable links."""
        formatter = SlackFormatter()
        
        answer = {
            "answer": "Our API uses REST principles.",
            "citations": [
                {
                    "source": "confluence",
                    "title": "API Design Guide",
                    "url": "https://example.atlassian.net/wiki/api",
                    "snippet": "RESTful API design principles"
                },
                {
                    "source": "github",
                    "title": "api-service/openapi.yaml",
                    "url": "https://github.com/org/api-service/blob/main/openapi.yaml",
                    "snippet": "OpenAPI specification"
                },
                {
                    "source": "jira",
                    "title": "API-123: Update API docs",
                    "url": "https://example.atlassian.net/browse/API-123",
                    "snippet": "Documentation updates"
                }
            ],
            "conversation_id": "conv-123"
        }
        
        blocks = formatter.format_answer(answer)
        blocks_str = str(blocks)
        
        # Check all URLs present
        assert "https://example.atlassian.net/wiki/api" in blocks_str
        assert "https://github.com/org/api-service" in blocks_str
        assert "https://example.atlassian.net/browse/API-123" in blocks_str
        
        # Check all titles present
        assert "API Design Guide" in blocks_str
        assert "api-service/openapi.yaml" in blocks_str
        assert "API-123" in blocks_str
    
    def test_citation_numbers(self):
        """Citations should be numbered [1], [2], etc."""
        formatter = SlackFormatter()
        
        answer = {
            "answer": "Test",
            "citations": [
                {"source": "slack", "title": "Doc 1", "url": "https://a.com"},
                {"source": "jira", "title": "Doc 2", "url": "https://b.com"},
                {"source": "github", "title": "Doc 3", "url": "https://c.com"}
            ],
            "conversation_id": "conv-123"
        }
        
        blocks = formatter.format_answer(answer)
        blocks_str = str(blocks)
        
        # Check numbering
        assert "[1]" in blocks_str
        assert "[2]" in blocks_str
        assert "[3]" in blocks_str
    
    def test_source_icons(self):
        """Citations should have source-specific icons."""
        formatter = SlackFormatter()
        
        sources = ["slack", "confluence", "jira", "github", "figma", "dropbox"]
        
        for source in sources:
            citation = {
                "source": source,
                "title": f"Test {source}",
                "url": f"https://example.com/{source}"
            }
            
            block = formatter.format_citation(citation, index=1)
            text = block["text"]["text"]
            
            # Should have emoji icon
            assert any(emoji in text for emoji in ["💬", "📄", "🎫", "🔧", "🎨", "📦", "📎"])
    
    def test_block_kit_structure(self):
        """Blocks should follow Slack Block Kit structure."""
        formatter = SlackFormatter()
        
        answer = {
            "answer": "Test answer",
            "citations": [
                {"source": "slack", "title": "Citation", "url": "https://example.com"}
            ],
            "conversation_id": "conv-123"
        }
        
        blocks = formatter.format_answer(answer)
        
        # Validate structure
        for block in blocks:
            assert "type" in block
            
            if block["type"] == "section":
                assert "text" in block
                assert block["text"]["type"] == "mrkdwn"
            
            if block["type"] == "context":
                assert "elements" in block
    
    def test_multiple_citations_with_deep_links(self):
        """Multiple citations should all have proper deep links."""
        formatter = SlackFormatter()
        
        answer = {
            "answer": "Information from multiple sources.",
            "citations": [
                {
                    "source": "slack",
                    "title": "Team discussion in #engineering",
                    "url": "https://workspace.slack.com/archives/C123/p1234567890",
                    "snippet": "Discussion about architecture"
                },
                {
                    "source": "confluence",
                    "title": "Architecture Decision Record",
                    "url": "https://example.atlassian.net/wiki/spaces/ENG/pages/456/ADR",
                    "snippet": "We chose microservices"
                },
                {
                    "source": "github",
                    "title": "PR #42: Implement microservices",
                    "url": "https://github.com/org/repo/pull/42",
                    "snippet": "Implementation PR"
                }
            ],
            "conversation_id": "conv-123"
        }
        
        blocks = formatter.format_answer(answer)
        
        # Count citation blocks
        citation_blocks = [b for b in blocks if b.get("type") == "section" and "[" in str(b)]
        assert len(citation_blocks) >= 3
        
        # All URLs should be present
        blocks_str = str(blocks)
        assert "workspace.slack.com" in blocks_str
        assert "atlassian.net" in blocks_str
        assert "github.com" in blocks_str
