"""Admin API routes for user management."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class IdentityMappingsResponse(BaseModel):
    """Response model for identity mappings."""
    user_id: int
    email: str
    connector_identities: dict[str, Any]

    model_config = {"from_attributes": True}


class IdentityMappingsUpdate(BaseModel):
    """Request model for updating identity mappings."""
    connector_identities: dict[str, dict[str, Any]]


@router.get("/users/{user_id}/identity-mappings", response_model=IdentityMappingsResponse)
def get_user_identity_mappings(
    user_id: int,
    db: Session = Depends(get_db),
) -> IdentityMappingsResponse:
    """Get user's connector identity mappings.

    Args:
        user_id: User ID
        db: Database session

    Returns:
        User's identity mappings for all connectors

    Raises:
        HTTPException: If user not found
    """
    user = db.query(User).filter_by(id=user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found"
        )

    return IdentityMappingsResponse(
        user_id=user.id,
        email=user.email,
        connector_identities=user.connector_identities or {}
    )


@router.patch("/users/{user_id}/identity-mappings", response_model=IdentityMappingsResponse)
def update_user_identity_mappings(
    user_id: int,
    update_data: IdentityMappingsUpdate,
    db: Session = Depends(get_db),
) -> IdentityMappingsResponse:
    """Update user's connector identity mappings.

    This endpoint allows administrators to map user identities across
    different connectors. Required for ACL validation to work correctly.

    Args:
        user_id: User ID
        update_data: New identity mappings
        db: Database session

    Returns:
        Updated user identity mappings

    Raises:
        HTTPException: If user not found or update fails

    Example:
        PATCH /v1/admin/users/1/identity-mappings
        {
            "connector_identities": {
                "slack": {
                    "user_id": "U123ABC",
                    "team_id": "T456DEF",
                    "display_name": "John Doe"
                },
                "github": {
                    "login": "johndoe",
                    "user_id": 12345,
                    "organizations": ["myorg", "otherorg"]
                }
            }
        }
    """
    user = db.query(User).filter_by(id=user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found"
        )

    try:
        # Merge new identities with existing ones
        current_identities = user.connector_identities or {}
        current_identities.update(update_data.connector_identities)

        user.connector_identities = current_identities

        db.commit()
        db.refresh(user)

        logger.info(
            f"Updated identity mappings for user {user_id}. "
            f"Connectors: {list(update_data.connector_identities.keys())}"
        )

        return IdentityMappingsResponse(
            user_id=user.id,
            email=user.email,
            connector_identities=user.connector_identities
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update identity mappings for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update identity mappings: {str(e)}"
        )
