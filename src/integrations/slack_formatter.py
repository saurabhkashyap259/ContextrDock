"""Slack message formatter for RAG answers and citations.

Formats answers and citations as Slack Block Kit messages with proper formatting,
clickable links, and user-friendly layout.
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SlackFormatter:
    """Format RAG responses for Slack Block Kit."""

    # Slack Block Kit limits
    MAX_BLOCK_TEXT_LENGTH = 3000
    MAX_BLOCKS_PER_MESSAGE = 50
    MAX_SNIPPET_LENGTH = 200

    # Source icons
    SOURCE_ICONS = {
        "slack": "💬",
        "confluence": "📄",
        "jira": "🎫",
        "github": "🔧",
        "figma": "🎨",
        "dropbox": "📦"
    }

    def format_answer(
        self,
        answer_data: dict[str, Any],
        include_feedback: bool = False
    ) -> list[dict[str, Any]]:
        """Format RAG answer with citations as Slack blocks.

        Args:
            answer_data: Dict with 'answer', 'citations', 'conversation_id'
            include_feedback: Whether to include feedback buttons

        Returns:
            List of Slack Block Kit blocks
        """
        blocks = []

        answer_text = answer_data.get("answer", "")
        citations = answer_data.get("citations", [])
        conversation_id = answer_data.get("conversation_id")
        has_more = answer_data.get("has_more_results", False)

        # Answer section
        if answer_text:
            formatted_answer = self.markdown_to_mrkdwn(answer_text)

            # Truncate if too long
            if len(formatted_answer) > self.MAX_BLOCK_TEXT_LENGTH:
                formatted_answer = formatted_answer[:self.MAX_BLOCK_TEXT_LENGTH - 50] + "... _(truncated)_"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": formatted_answer
                }
            })
        else:
            # Empty answer - show message
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_No answer available._"
                }
            })

        # Citations section
        if citations:
            # Divider
            blocks.append({"type": "divider"})

            # Citations header
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📚 *Sources* ({len(citations)})"
                    }
                ]
            })

            # Individual citations
            for idx, citation in enumerate(citations[:10], 1):  # Limit to 10 citations
                citation_block = self.format_citation(citation, idx)
                if citation_block:
                    blocks.append(citation_block)

            if len(citations) > 10:
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"_+{len(citations) - 10} more sources_"
                        }
                    ]
                })

        # More results indicator
        if has_more:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 _Additional results available. Try refining your question._"
                    }
                ]
            })

        # Metadata footer
        if conversation_id:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Conversation ID: `{conversation_id}`"
                    }
                ]
            })

        # Feedback buttons
        if include_feedback:
            feedback_block = self._create_feedback_buttons(conversation_id)
            if feedback_block:
                blocks.append(feedback_block)

        return blocks[:self.MAX_BLOCKS_PER_MESSAGE]

    def format_citation(self, citation: dict[str, Any], index: int) -> Optional[dict[str, Any]]:
        """Format a single citation as a Slack block.

        Args:
            citation: Citation dict with source, title, url, snippet
            index: Citation number (1-based)

        Returns:
            Slack section block or None if invalid
        """
        source = citation.get("source", "unknown")
        title = citation.get("title", "Untitled")
        url = citation.get("url")
        snippet = citation.get("snippet", "")

        # Get source icon
        icon = self.SOURCE_ICONS.get(source, "📎")

        # Format title with link
        if url:
            title_text = f"<{url}|{title}>"
        else:
            title_text = title

        # Build citation text
        citation_text = f"{icon} *[{index}]* {title_text}"

        # Add snippet if available
        if snippet:
            # Truncate snippet
            if len(snippet) > self.MAX_SNIPPET_LENGTH:
                snippet = snippet[:self.MAX_SNIPPET_LENGTH] + "..."

            citation_text += f"\n_{snippet}_"

        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": citation_text
            }
        }

    def markdown_to_mrkdwn(self, text: str) -> str:
        """Convert markdown to Slack mrkdwn format.

        Args:
            text: Markdown text

        Returns:
            Slack mrkdwn formatted text
        """
        # Convert **bold** to *bold*
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)

        # Slack supports both * and _ for emphasis
        # Keep code blocks as is (```...```)
        # Keep inline code as is (`...`)

        # Convert markdown links [text](url) to <url|text>
        text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<\2|\1>', text)

        return text

    def format_error(self, error_message: str) -> list[dict[str, Any]]:
        """Format error message for user.

        Args:
            error_message: Technical error message

        Returns:
            List of Slack blocks with user-friendly error
        """
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ *Sorry, I encountered an issue processing your request.*\n\n"
                           "Please try again in a moment. If the problem persists, "
                           "contact your administrator."
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_If you need immediate help, try rephrasing your question._"
                    }
                ]
            }
        ]

    def format_no_results(self) -> list[dict[str, Any]]:
        """Format 'no results found' message.

        Returns:
            List of Slack blocks
        """
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔍 *I couldn't find specific information about that.*\n\n"
                           "Try:\n"
                           "• Rephrasing your question\n"
                           "• Using different keywords\n"
                           "• Checking if the information exists in your connected tools"
                }
            }
        ]

    def format_rate_limit(self) -> list[dict[str, Any]]:
        """Format rate limit message.

        Returns:
            List of Slack blocks
        """
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⏱️ *You're making requests too quickly.*\n\n"
                           "Please wait a moment before trying again."
                }
            }
        ]

    def format_dm_suggestion(self, user_id: str) -> list[dict[str, Any]]:
        """Format suggestion to use DM for privacy.

        Args:
            user_id: Slack user ID

        Returns:
            List of Slack blocks (ephemeral message)
        """
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔒 *For privacy, please ask me in a DM*\n\n"
                           "Your question may retrieve confidential information. "
                           "Click my name to send me a direct message."
                }
            }
        ]

    def _create_feedback_buttons(self, conversation_id: Optional[str]) -> Optional[dict[str, Any]]:
        """Create feedback action buttons.

        Args:
            conversation_id: Conversation ID for tracking

        Returns:
            Actions block or None
        """
        if not conversation_id:
            return None

        return {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "👍 Helpful"
                    },
                    "value": f"feedback_positive_{conversation_id}",
                    "action_id": "feedback_positive"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "👎 Not Helpful"
                    },
                    "value": f"feedback_negative_{conversation_id}",
                    "action_id": "feedback_negative"
                }
            ]
        }


def format_help_message() -> list[dict[str, Any]]:
    """Format help message explaining how to use the bot.

    Returns:
        List of Slack blocks
    """
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🤖 How to Use ContextDock"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Ways to ask questions:*\n"
                       "• Send me a DM with your question\n"
                       "• Use `/ask <your question>` in any channel\n"
                       "• Mention me in a private channel\n\n"
                       "*What I can do:*\n"
                       "• Search across all your connected tools\n"
                       "• Provide answers with citations and links\n"
                       "• Respect your access permissions\n\n"
                       "*Privacy:*\n"
                       "• I'll suggest using DM for sensitive queries in public channels\n"
                       "• You only see information you have access to"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 _Tip: Be specific in your questions for better results_"
                }
            ]
        }
    ]
