"""
JWT authentication and security utilities.
"""
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import get_settings

settings = get_settings()
security_scheme = HTTPBearer()


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a JWT access token.
    
    Args:
        subject: The subject (usually username or service name)
        expires_delta: Optional expiration time delta
        additional_claims: Additional claims to include in token
    
    Returns:
        Encoded JWT token
    """
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expiration_minutes)
    
    to_encode = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    
    if additional_claims:
        to_encode.update(additional_claims)
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def create_service_token(service_name: str) -> str:
    """
    Create a service-to-service JWT token.
    
    Args:
        service_name: Name of the service (e.g., 'django-web-service')
    
    Returns:
        JWT token
    """
    return create_access_token(
        subject=service_name,
        additional_claims={"type": "service"}
    )


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security_scheme)) -> Dict[str, Any]:
    """
    Verify JWT token from Authorization header.
    
    Args:
        credentials: HTTP authorization credentials
    
    Returns:
        Decoded token payload
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(token_payload: Dict[str, Any] = Security(verify_token)) -> str:
    """
    Get current user/service from token.
    
    Args:
        token_payload: Decoded JWT payload
    
    Returns:
        Subject (username or service name)
    """
    subject = token_payload.get("sub")
    
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: no subject found"
        )
    
    return subject