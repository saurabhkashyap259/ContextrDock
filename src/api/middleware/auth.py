"""Authentication middleware for FastAPI."""


from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.services.auth import verify_token

# HTTP Bearer token scheme
security = HTTPBearer()


class AuthenticatedUser(BaseModel):
    """Authenticated user information."""

    user_id: int
    email: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthenticatedUser:
    """
    Dependency to get the current authenticated user from Bearer token.

    Args:
        credentials: HTTP Authorization credentials (Bearer token)

    Returns:
        AuthenticatedUser with user_id and email

    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    token = credentials.credentials

    # Verify token
    token_data = verify_token(token, expected_type="access")

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(user_id=token_data.user_id, email=token_data.email)
