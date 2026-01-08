"""Tests for Slack message formatter.

Tests formatting answers and citations as Slack Block Kit messages.
"""

import pytest
from typing import Dict, List, Any


@pytest.fixture
def sample_answer():
    """Sample RAG answer with citations."""
    return {
        "answer": "The authentication system uses **OAuth2** with JWT tokens. "
                 "Access tokens expire after 15 minutes, while refresh tokens last 7 days. "
                 "The system supports multiple providers including Google and GitHub.",
        "citations": [
            {
                "source": "confluence",
                "title": "Authentication Architecture",
                "url": "https://example.atlassian.net/wiki/spaces/ENG/pages/123/Auth",
                "snippet": "OAuth2 provides secure token-based authentication with configurable expiry times."
            },
            {
                "source": "github",
                "title": "auth-service/README.md",
                "url": "https://github.com/myorg/auth-service/blob/main/README.md",
                "snippet": "JWT tokens are signed using RS256 algorithm with rotating keys."
            }
        ],
        "conversation_id": "conv-123"
    }


@pytest.fixture
def slack_formatter():
    """Create Slack formatter instance."""
    from src.integrations.slack_formatter import SlackFormatter
    return SlackFormatter()


class TestSlackFormatterBasicFormatting:
    """Test basic message formatting."""
    
    def test_format_answer_with_citations(self, slack_formatter, sample_answer):
        """Should format answer and citations as Slack blocks."""
        blocks = slack_formatter.format_answer(sample_answer)
        
        assert isinstance(blocks, list)
        assert len(blocks) > 0
        
        # Should have answer section
        answer_block = next(b for b in blocks if b.get("type") == "section")
        assert "OAuth2" in answer_block["text"]["text"]
        
        # Should have citations section
        citation_blocks = [b for b in blocks if "citation" in str(b).lower() or "source" in str(b).lower()]
        assert len(citation_blocks) >= 2  # Two citations
    
    def test_markdown_to_slack_mrkdwn(self, slack_formatter):
        """Should convert markdown to Slack mrkdwn format."""
        text = "The **bold text** and *italic text* with `code`."
        
        formatted = slack_formatter.markdown_to_mrkdwn(text)
        
        # Slack uses * for bold and _ for italic
        assert "*bold text*" in formatted
        assert "_italic text_" in formatted or "*italic text*" in formatted  # Slack supports both
        assert "`code`" in formatted
    
    def test_answer_with_no_citations(self, slack_formatter):
        """Should handle answers without citations."""
        answer = {
            "answer": "I couldn't find specific information about that topic.",
            "citations": [],
            "conversation_id": "conv-123"
        }
        
        blocks = slack_formatter.format_answer(answer)
        
        # Should still create blocks
        assert len(blocks) > 0
        
        # Should have answer
        answer_text = str(blocks)
        assert "couldn't find" in answer_text
    
    def test_long_answer_truncation(self, slack_formatter):
        """Should truncate very long answers appropriately."""
        long_text = "A" * 5000  # 5000 chars, exceeds Slack block text limit
        answer = {
            "answer": long_text,
            "citations": [],
            "conversation_id": "conv-123"
        }
        
        blocks = slack_formatter.format_answer(answer)
        
        # Should not exceed Slack limits
        for block in blocks:
            if block.get("type") == "section" and "text" in block:
                assert len(block["text"]["text"]) <= 3000  # Slack block text limit


class TestSlackFormatterCitations:
    """Test citation formatting."""
    
    def test_format_single_citation(self, slack_formatter):
        """Should format a single citation block."""
        citation = {
            "source": "confluence",
            "title": "Authentication Architecture",
            "url": "https://example.atlassian.net/wiki/spaces/ENG/pages/123/Auth",
            "snippet": "OAuth2 provides secure token-based authentication."
        }
        
        block = slack_formatter.format_citation(citation, index=1)
        
        assert block["type"] == "section"
        
        # Should have clickable link
        text = block["text"]["text"]
        assert "Authentication Architecture" in text
        assert "https://example.atlassian.net" in text
        
        # Should have citation number
        assert "[1]" in text or "1." in text
        
        # Should have source icon or label
        assert "confluence" in text.lower() or "📄" in text
    
    def test_format_multiple_citations(self, slack_formatter, sample_answer):
        """Should format multiple citations with numbering."""
        blocks = slack_formatter.format_answer(sample_answer)
        
        # Find citation blocks
        citation_text = str(blocks)
        
        # Should have numbered citations
        assert "[1]" in citation_text or "1." in citation_text
        assert "[2]" in citation_text or "2." in citation_text
        
        # Should have both source titles
        assert "Authentication Architecture" in citation_text
        assert "auth-service/README.md" in citation_text
    
    def test_citation_with_missing_fields(self, slack_formatter):
        """Should handle citations with missing optional fields."""
        citation = {
            "source": "slack",
            "title": "Team Discussion",
            "url": "https://workspace.slack.com/archives/C123/p1234567890"
            # Missing snippet
        }
        
        block = slack_formatter.format_citation(citation, index=1)
        
        assert block["type"] == "section"
        assert "Team Discussion" in block["text"]["text"]
        # Should not crash without snippet
    
    def test_citation_url_formatting(self, slack_formatter):
        """Should create clickable links for citations."""
        citation = {
            "source": "github",
            "title": "Pull Request #123",
            "url": "https://github.com/myorg/repo/pull/123",
            "snippet": "Fix authentication bug"
        }
        
        block = slack_formatter.format_citation(citation, index=1)
        
        text = block["text"]["text"]
        
        # Slack link format: <URL|Text>
        assert "<https://github.com/myorg/repo/pull/123|" in text or \
               "https://github.com/myorg/repo/pull/123" in text
    
    def test_citation_source_icons(self, slack_formatter):
        """Should add appropriate icons/labels for different sources."""
        sources_and_icons = [
            ("slack", "💬"),
            ("confluence", "📄"),
            ("jira", "🎫"),
            ("github", "🔧"),
            ("figma", "🎨"),
            ("dropbox", "📦")
        ]
        
        for source, expected_icon in sources_and_icons:
            citation = {
                "source": source,
                "title": f"Test {source}",
                "url": f"https://example.com/{source}",
                "snippet": "Test snippet"
            }
            
            block = slack_formatter.format_citation(citation, index=1)
            text = block["text"]["text"]
            
            # Should have icon or source name
            assert expected_icon in text or source.capitalize() in text


class TestSlackFormatterBlocks:
    """Test Slack Block Kit structure."""
    
    def test_blocks_have_valid_structure(self, slack_formatter, sample_answer):
        """All blocks should follow Slack Block Kit schema."""
        blocks = slack_formatter.format_answer(sample_answer)
        
        for block in blocks:
            # Must have type
            assert "type" in block
            assert block["type"] in ["section", "divider", "header", "context", "actions"]
            
            # Sections must have text
            if block["type"] == "section":
                assert "text" in block
                assert "type" in block["text"]
                assert block["text"]["type"] == "mrkdwn"
    
    def test_divider_between_sections(self, slack_formatter, sample_answer):
        """Should use dividers to separate answer from citations."""
        blocks = slack_formatter.format_answer(sample_answer)
        
        # Should have at least one divider
        dividers = [b for b in blocks if b.get("type") == "divider"]
        assert len(dividers) >= 1
    
    def test_header_block_for_citations(self, slack_formatter, sample_answer):
        """Should have header block for citations section."""
        blocks = slack_formatter.format_answer(sample_answer)
        
        # May have header or context block for citations
        header_or_context = [
            b for b in blocks 
            if b.get("type") in ["header", "context"] and 
            ("source" in str(b).lower() or "citation" in str(b).lower())
        ]
        
        # Should have some kind of citations label
        blocks_text = str(blocks)
        assert "source" in blocks_text.lower() or "citation" in blocks_text.lower()
    
    def test_context_block_for_metadata(self, slack_formatter, sample_answer):
        """Should include context block with metadata."""
        blocks = slack_formatter.format_answer(sample_answer)
        
        # Look for context blocks (typically at the end)
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        
        # Should have conversation ID or other metadata
        if context_blocks:
            context_text = str(context_blocks)
            assert "conv-" in context_text or "conversation" in context_text.lower()


class TestSlackFormatterSpecialCases:
    """Test edge cases and special formatting."""
    
    def test_empty_answer(self, slack_formatter):
        """Should handle empty answer gracefully."""
        answer = {
            "answer": "",
            "citations": [],
            "conversation_id": "conv-123"
        }
        
        blocks = slack_formatter.format_answer(answer)
        
        # Should return valid blocks (maybe error message)
        assert isinstance(blocks, list)
        assert len(blocks) > 0
    
    def test_answer_with_code_blocks(self, slack_formatter):
        """Should preserve code blocks in answer."""
        answer = {
            "answer": "Here's an example:\n```python\nprint('Hello')\n```",
            "citations": [],
            "conversation_id": "conv-123"
        }
        
        blocks = slack_formatter.format_answer(answer)
        
        blocks_text = str(blocks)
        
        # Slack code blocks use triple backticks
        assert "```" in blocks_text
        assert "python" in blocks_text or "Hello" in blocks_text
    
    def test_answer_with_lists(self, slack_formatter):
        """Should format lists appropriately."""
        answer = {
            "answer": "Features:\n- OAuth2 authentication\n- JWT tokens\n- Role-based access",
            "citations": [],
            "conversation_id": "conv-123"
        }
        
        blocks = slack_formatter.format_answer(answer)
        
        blocks_text = str(blocks)
        
        # Should preserve list formatting
        assert "OAuth2" in blocks_text
        assert "JWT" in blocks_text
        assert "-" in blocks_text or "•" in blocks_text or "*" in blocks_text
    
    def test_answer_with_urls(self, slack_formatter):
        """Should format URLs as clickable links."""
        answer = {
            "answer": "Check the docs at https://example.com/docs for more info.",
            "citations": [],
            "conversation_id": "conv-123"
        }
        
        blocks = slack_formatter.format_answer(answer)
        
        blocks_text = str(blocks)
        
        # URL should be present (may be formatted as Slack link)
        assert "https://example.com/docs" in blocks_text or \
               "<https://example.com/docs" in blocks_text
    
    def test_citation_snippet_truncation(self, slack_formatter):
        """Should truncate very long citation snippets."""
        citation = {
            "source": "confluence",
            "title": "Long Document",
            "url": "https://example.com",
            "snippet": "A" * 500  # 500 chars
        }
        
        block = slack_formatter.format_citation(citation, index=1)
        
        text = block["text"]["text"]
        
        # Snippet should be truncated with ellipsis
        if "A" * 500 in text:
            pytest.fail("Snippet should be truncated")
        
        # Should have reasonable length
        assert len(text) < 500


class TestSlackFormatterErrorHandling:
    """Test error message formatting."""
    
    def test_format_error_message(self, slack_formatter):
        """Should format error messages user-friendly."""
        error_msg = "Database connection failed"
        
        blocks = slack_formatter.format_error(error_msg)
        
        assert isinstance(blocks, list)
        assert len(blocks) > 0
        
        blocks_text = str(blocks)
        
        # Should have user-friendly message (not raw error)
        assert "sorry" in blocks_text.lower() or "error" in blocks_text.lower()
        
        # Should not expose technical details
        assert "Database" not in blocks_text or "issue" in blocks_text.lower()
    
    def test_format_no_results_found(self, slack_formatter):
        """Should format 'no results' message helpfully."""
        blocks = slack_formatter.format_no_results()
        
        blocks_text = str(blocks)
        
        # Should be helpful
        assert "couldn't find" in blocks_text.lower() or \
               "no information" in blocks_text.lower() or \
               "try rephrasing" in blocks_text.lower()
    
    def test_format_rate_limit_message(self, slack_formatter):
        """Should format rate limit message."""
        blocks = slack_formatter.format_rate_limit()
        
        blocks_text = str(blocks)
        
        # Should explain rate limit
        assert "too many" in blocks_text.lower() or \
               "rate limit" in blocks_text.lower() or \
               "wait" in blocks_text.lower()


class TestSlackFormatterActionButtons:
    """Test action buttons in messages."""
    
    def test_add_feedback_buttons(self, slack_formatter, sample_answer):
        """Should add feedback buttons (helpful/not helpful)."""
        blocks = slack_formatter.format_answer(sample_answer, include_feedback=True)
        
        # Look for actions block
        action_blocks = [b for b in blocks if b.get("type") == "actions"]
        
        if action_blocks:
            actions = action_blocks[0]["elements"]
            
            # Should have feedback buttons
            assert len(actions) >= 2
            
            # Check button values
            button_texts = [a.get("text", {}).get("text", "") for a in actions]
            assert any("helpful" in text.lower() for text in button_texts)
    
    def test_add_view_more_button(self, slack_formatter):
        """Should add 'View More' button if results are truncated."""
        answer = {
            "answer": "Short answer",
            "citations": [{"source": "slack", "title": f"Doc {i}", "url": f"https://example.com/{i}"} 
                         for i in range(10)],  # Many citations
            "conversation_id": "conv-123",
            "has_more_results": True
        }
        
        blocks = slack_formatter.format_answer(answer)
        
        blocks_text = str(blocks)
        
        # Should have indication of more results
        assert "more" in blocks_text.lower() or "additional" in blocks_text.lower()


class TestSlackFormatterPrivacyMessages:
    """Test privacy-related message formatting."""
    
    def test_format_dm_suggestion(self, slack_formatter):
        """Should format suggestion to use DM."""
        blocks = slack_formatter.format_dm_suggestion(user_id="U123")
        
        blocks_text = str(blocks)
        
        # Should suggest DM
        assert "DM" in blocks_text or "direct message" in blocks_text.lower()
        
        # Should mention privacy
        assert "private" in blocks_text.lower() or "confidential" in blocks_text.lower()
        
        # Should have clickable link to DM bot
        assert "<@" in blocks_text or "message me" in blocks_text.lower()
    
    def test_format_ephemeral_response(self, slack_formatter):
        """Should format ephemeral responses properly."""
        blocks = slack_formatter.format_dm_suggestion(user_id="U123")
        
        # Ephemeral messages should be concise
        assert len(blocks) <= 3
        
        # Should only be visible to user
        blocks_text = str(blocks)
        assert "only you" in blocks_text.lower() or "private" in blocks_text.lower() or \
               len(blocks_text) < 500  # Concise
