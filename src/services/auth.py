"""JWT authentication service."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from pydantic import BaseModel

from src.config import settings


class TokenData(BaseModel):
    """Token payload data."""

    email: str
    user_id: int
    token_type: str  # "access" or "refresh"


def create_access_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT access token with 15-minute expiration.
    
    Args:
        data: Dictionary containing token payload (must include "sub" for email)
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    })
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT refresh token with 7-day expiration.
    
    Args:
        data: Dictionary containing token payload (must include "sub" for email)
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
    })
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def verify_token(token: str, expected_type: str = "access") -> Optional[TokenData]:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token string to verify
        expected_type: Expected token type ("access" or "refresh")
        
    Returns:
        TokenData if valid, None if invalid/expired
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        
        email: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        token_type: str = payload.get("type")
        
        if email is None or user_id is None:
            return None
            
        if token_type != expected_type:
            return None
            
        return TokenData(email=email, user_id=user_id, token_type=token_type)
        
    except JWTError:
        return None


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode a JWT token without validation (for debugging/inspection).
    
    Args:
        token: JWT token string to decode
        
    Returns:
        Decoded payload dictionary if successful, None if invalid format
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None
