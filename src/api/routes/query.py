"""Query API routes for asking questions."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas.query import QueryRequest, QueryResponse, Citation
from src.api.middleware.auth import get_current_user
from src.models.user import User
from src.models.conversation import Conversation
from src.models.message import Message
from src.database import get_db
from src.integrations.llm_client import OpenAIClient
from src.retrieval.answer_generation import generate_answer
from src.config.settings import settings


router = APIRouter(prefix="/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse, status_code=status.HTTP_200_OK)
def query_knowledge_base(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QueryResponse:
    """
    Query the knowledge base with a natural language question.
    
    This endpoint:
    1. Creates or continues a conversation
    2. Retrieves relevant document chunks (permission-aware)
    3. Generates an answer using LLM with RAG
    4. Stores the question and answer as messages
    5. Returns answer with grounded citations
    
    Args:
        request: Query request with question and options
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Answer with citations and conversation metadata
        
    Raises:
        404: Conversation not found or doesn't belong to user
        500: LLM or retrieval error
    """
    # Step 1: Get or create conversation
    if request.conversation_id:
        conversation = db.query(Conversation).filter(
            Conversation.id == request.conversation_id,
            Conversation.workspace_id == current_user.workspace_id,
            Conversation.user_id == current_user.id,
        ).first()
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied"
            )
    else:
        # Create new conversation
        conversation = Conversation(
            workspace_id=current_user.workspace_id,
            user_id=current_user.id,
            channel_type="web",
            external_channel_id=None,
        )
        db.add(conversation)
        db.flush()
    
    # Step 2: Store user's question
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.question,
        citations_json=None,
    )
    db.add(user_message)
    db.flush()
    
    # Step 3: Generate answer with RAG
    try:
        llm_client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
        
        result = generate_answer(
            db_session=db,
            query=request.question,
            user_id=current_user.id,
            workspace_id=current_user.workspace_id,
            llm_client=llm_client,
            max_context_chunks=request.max_results,
            temperature=request.temperature,
        )
    except Exception as e:
        # Log error (in production, use proper logging)
        print(f"Error generating answer: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate answer"
        )
    
    # Step 4: Store assistant's answer
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result["answer"],
        citations_json=result["citations"],
    )
    db.add(assistant_message)
    db.commit()
    
    # Step 5: Build response
    citations = [
        Citation(
            chunk_id=c["chunk_id"],
            document_id=c["document_id"],
            title=c.get("title"),
            url=c.get("url"),
            score=c["score"],
        )
        for c in result["citations"]
    ]
    
    return QueryResponse(
        answer=result["answer"],
        citations=citations,
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        usage=result["usage"],
    )
