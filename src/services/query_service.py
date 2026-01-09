"""Query service for handling search requests."""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.integrations.llm_client import OpenAIClient
from src.retrieval.answer_generation import generate_answer
from src.config.settings import settings

logger = logging.getLogger(__name__)


class QueryService:
    """Service for handling query requests."""

    def __init__(self):
        """Initialize query service."""
        self.llm_client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )

    async def query(
        self,
        question: str,
        user_id: str,
        user_email: Optional[str] = None,
        channel_id: Optional[str] = None,
        workspace_id: int = 1,  # Default workspace
        max_results: int = 10,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        Execute query against knowledge base.

        Args:
            question: User's question
            user_id: User ID (Slack user ID)
            user_email: User email for identity resolution
            channel_id: Channel ID for context
            workspace_id: Workspace ID for filtering
            max_results: Maximum number of results to return
            temperature: LLM temperature

        Returns:
            Dict with 'answer', 'citations', and metadata
        """
        db: Session = SessionLocal()
        
        try:
            # For now, use a simple user mapping
            # In production, resolve Slack user ID to ContextDock user ID
            contextdock_user_id = 1  # Default admin user
            
            # Generate answer using RAG
            result = generate_answer(
                db_session=db,
                query=question,
                user_id=contextdock_user_id,
                workspace_id=workspace_id,
                llm_client=self.llm_client,
                max_context_chunks=max_results,
                temperature=temperature,
            )
            
            # Format citations for Slack
            formatted_citations = []
            for citation in result.get("citations", []):
                formatted_citations.append({
                    "source": citation.get("source_type", "unknown"),
                    "title": citation.get("title", "Untitled"),
                    "url": citation.get("url", ""),
                    "snippet": citation.get("content", "")[:200],
                    "score": citation.get("score", 0.0),
                })
            
            return {
                "answer": result["answer"],
                "citations": formatted_citations,
                "conversation_id": None,  # Optional: track conversations
                "usage": result.get("usage", {}),
            }
            
        except Exception as e:
            logger.error(f"Error in query service: {e}", exc_info=True)
            raise
        finally:
            db.close()
