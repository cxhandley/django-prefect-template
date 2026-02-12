"""
Tests for JWT authentication and security utilities.
"""
from datetime import datetime, timedelta, UTC
from unittest.mock import patch, MagicMock
import pytest
import jwt
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from core.security import (
    create_access_token,
    create_service_token,
    verify_token,
    get_current_user,
    security_scheme,
)


# Mock settings
@pytest.fixture
def mock_settings():
    """Mock settings for JWT operations."""
    with patch('core.security.settings') as settings:
        settings.jwt_secret = "test-secret-key-that-is-very-long"
        settings.jwt_algorithm = "HS256"
        settings.jwt_expiration_minutes = 30
        yield settings


class TestCreateAccessToken:
    """Tests for create_access_token function."""
    
    def test_create_access_token_default_expiration(self, mock_settings):
        """Test creating token with default expiration."""
        token = create_access_token(subject="test-user")
        
        assert token
        assert isinstance(token, str)
        
        # Decode and verify
        payload = jwt.decode(
            token,
            mock_settings.jwt_secret,
            algorithms=[mock_settings.jwt_algorithm]
        )
        assert payload["sub"] == "test-user"
        assert "exp" in payload
        assert "iat" in payload
    
    def test_create_access_token_custom_expiration(self, mock_settings):
        """Test creating token with custom expiration."""
        custom_delta = timedelta(hours=1)
        token = create_access_token(
            subject="test-user",
            expires_delta=custom_delta
        )
        
        payload = jwt.decode(
            token,
            mock_settings.jwt_secret,
            algorithms=[mock_settings.jwt_algorithm]
        )
        
        # Check expiration is approximately 1 hour from now
        iat = payload["iat"]
        exp = payload["exp"]
        exp_delta_seconds = exp - iat
        
        assert 3500 < exp_delta_seconds < 3700  # ~1 hour with some tolerance
    
    def test_create_access_token_with_additional_claims(self, mock_settings):
        """Test creating token with additional claims."""
        additional_claims = {
            "type": "service",
            "permissions": ["read", "write"]
        }
        token = create_access_token(
            subject="test-service",
            additional_claims=additional_claims
        )
        
        payload = jwt.decode(
            token,
            mock_settings.jwt_secret,
            algorithms=[mock_settings.jwt_algorithm]
        )
        
        assert payload["sub"] == "test-service"
        assert payload["type"] == "service"
        assert payload["permissions"] == ["read", "write"]
    
    def test_create_access_token_issued_at_timestamp(self, mock_settings):
        """Test that token includes issued at timestamp."""
        before = datetime.now(UTC).replace(microsecond=0)
        token = create_access_token(subject="test-user")
        after = datetime.now(UTC).replace(microsecond=0)
        
        payload = jwt.decode(
            token,
            mock_settings.jwt_secret,
            algorithms=[mock_settings.jwt_algorithm]
        )
        
        # iat should be between before and after
        iat_datetime = datetime.fromtimestamp(payload["iat"], tz=UTC)
        assert before <= iat_datetime <= after


class TestCreateServiceToken:
    """Tests for create_service_token function."""
    
    def test_create_service_token(self, mock_settings):
        """Test creating a service token."""
        service_name = "django-web-service"
        token = create_service_token(service_name)
        
        assert token
        assert isinstance(token, str)
        
        payload = jwt.decode(
            token,
            mock_settings.jwt_secret,
            algorithms=[mock_settings.jwt_algorithm]
        )
        
        assert payload["sub"] == service_name
        assert payload["type"] == "service"
    
    def test_create_service_token_multiple_services(self, mock_settings):
        """Test creating tokens for different services."""
        services = ["service-a", "service-b", "service-c"]
        
        for service in services:
            token = create_service_token(service)
            payload = jwt.decode(
                token,
                mock_settings.jwt_secret,
                algorithms=[mock_settings.jwt_algorithm]
            )
            
            assert payload["sub"] == service
            assert payload["type"] == "service"


class TestVerifyToken:
    """Tests for verify_token function."""
    
    def test_verify_token_valid(self, mock_settings):
        """Test verifying a valid token."""
        token = create_access_token(subject="test-user")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        payload = verify_token(credentials)
        
        assert payload["sub"] == "test-user"
        assert "exp" in payload
        assert "iat" in payload
    
    def test_verify_token_expired(self, mock_settings):
        """Test verifying an expired token."""
        # Create token with past expiration
        expired_delta = timedelta(minutes=-1)
        token = create_access_token(
            subject="test-user",
            expires_delta=expired_delta
        )
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(credentials)
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
    
    def test_verify_token_invalid_signature(self, mock_settings):
        """Test verifying a token with invalid signature."""
        # Create token with one secret, try to verify with another
        token = create_access_token(subject="test-user")
        
        # Tamper with the token
        tampered_token = token[:-10] + "tampered00"
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=tampered_token)
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(credentials)
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "validate" in exc_info.value.detail.lower()
    
    def test_verify_token_malformed(self, mock_settings):
        """Test verifying a malformed token."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.token")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(credentials)
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_verify_token_empty_string(self, mock_settings):
        """Test verifying an empty token."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="")
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(credentials)
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_verify_token_with_additional_claims(self, mock_settings):
        """Test verifying token with additional claims."""
        claims = {"type": "service", "org": "acme"}
        token = create_access_token(
            subject="test-service",
            additional_claims=claims
        )
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        payload = verify_token(credentials)
        
        assert payload["sub"] == "test-service"
        assert payload["type"] == "service"
        assert payload["org"] == "acme"


class TestGetCurrentUser:
    """Tests for get_current_user function."""
    
    def test_get_current_user_from_valid_token(self, mock_settings):
        """Test extracting user from valid token."""
        token = create_access_token(subject="test-user")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        payload = verify_token(credentials)
        user = get_current_user(payload)
        
        assert user == "test-user"
    
    def test_get_current_user_service_token(self, mock_settings):
        """Test extracting service name from service token."""
        token = create_service_token("my-service")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        payload = verify_token(credentials)
        service = get_current_user(payload)
        
        assert service == "my-service"
    
    def test_get_current_user_missing_subject(self, mock_settings):
        """Test error when token has no subject."""
        # Create a token payload without 'sub'
        token_payload = {"exp": (datetime.now(UTC) + timedelta(minutes=30)).timestamp()}
        
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(token_payload)
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "subject" in exc_info.value.detail.lower()
    
    def test_get_current_user_none_subject(self, mock_settings):
        """Test error when subject is None."""
        token_payload = {"sub": None, "exp": (datetime.now(UTC) + timedelta(minutes=30)).timestamp()}
        
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(token_payload)
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_current_user_empty_subject(self, mock_settings):
        """Test error when subject is empty string."""
        token_payload = {"sub": "", "exp": (datetime.now(UTC) + timedelta(minutes=30)).timestamp()}
        
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(token_payload)
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


class TestIntegration:
    """Integration tests for the full auth flow."""
    
    def test_full_auth_flow_user(self, mock_settings):
        """Test complete authentication flow for user."""
        # Create token
        username = "john-doe"
        token = create_access_token(subject=username)
        
        # Verify token
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = verify_token(credentials)
        
        # Extract user
        user = get_current_user(payload)
        
        assert user == username
    
    def test_full_auth_flow_service(self, mock_settings):
        """Test complete authentication flow for service."""
        # Create service token
        service_name = "notification-service"
        token = create_service_token(service_name)
        
        # Verify token
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = verify_token(credentials)
        
        # Extract service name
        service = get_current_user(payload)
        
        assert service == service_name
        assert payload["type"] == "service"
    
    def test_auth_flow_with_custom_expiration(self, mock_settings):
        """Test auth flow with custom token expiration."""
        custom_delta = timedelta(hours=2)
        token = create_access_token(
            subject="test-user",
            expires_delta=custom_delta
        )
        
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = verify_token(credentials)
        user = get_current_user(payload)
        
        assert user == "test-user"
        
        # Verify expiration is about 2 hours
        exp_delta = payload["exp"] - payload["iat"]
        assert 7000 < exp_delta < 7300  # ~2 hours
    
    def test_token_invalidation_scenario(self, mock_settings):
        """Test scenario where token becomes invalid."""
        token = create_access_token(subject="test-user")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # First verification succeeds
        payload = verify_token(credentials)
        assert payload["sub"] == "test-user"
        
        # Simulate token tampering
        tampered = token[:-5] + "xxxxx"
        bad_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=tampered)
        
        # Second verification fails
        with pytest.raises(HTTPException):
            verify_token(bad_credentials)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_token_with_special_characters_in_subject(self, mock_settings):
        """Test token with special characters in subject."""
        subject = "user+test@example.com"
        token = create_access_token(subject=subject)
        
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = verify_token(credentials)
        
        assert payload["sub"] == subject
    
    def test_token_with_unicode_subject(self, mock_settings):
        """Test token with unicode characters."""
        subject = "用户-test-ユーザー"
        token = create_access_token(subject=subject)
        
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = verify_token(credentials)
        
        assert payload["sub"] == subject
    
    def test_multiple_additional_claims(self, mock_settings):
        """Test token with multiple additional claims."""
        claims = {
            "type": "user",
            "org": "acme",
            "roles": ["admin", "user"],
            "permissions": {"read": True, "write": False},
            "level": 5
        }
        token = create_access_token(
            subject="test-user",
            additional_claims=claims
        )
        
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = verify_token(credentials)
        
        assert payload["org"] == "acme"
        assert payload["roles"] == ["admin", "user"]
        assert payload["permissions"]["read"] is True
        assert payload["level"] == 5
    
    def test_zero_expiration_delta(self, mock_settings):
        """Test token with zero expiration delta."""
        token = create_access_token(
            subject="test-user",
            expires_delta=timedelta(seconds=0)
        )
        
        # Token should expire immediately (or be very close)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # May or may not raise depending on timing, but should be near expiration
        try:
            payload = verify_token(credentials)
            # If it doesn't raise, the token is at least valid
            assert payload["sub"] == "test-user"
        except HTTPException:
            # Token already expired, which is acceptable
            pass
    
    def test_very_long_expiration(self, mock_settings):
        """Test token with very long expiration."""
        long_delta = timedelta(days=365)
        token = create_access_token(
            subject="test-user",
            expires_delta=long_delta
        )
        
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = verify_token(credentials)
        
        assert payload["sub"] == "test-user"
        exp_delta = payload["exp"] - payload["iat"]
        assert exp_delta > 31000000  # More than 365 days in seconds