import os
import pytest
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Set up test environment
os.environ["ENV"] = "development"
os.environ["JWT_SECRET"] = "test_env_secret_key_12345"

# Import app and auth middleware
from api.main import app
from api.middleware import auth

client = TestClient(app)


def test_token_creation_and_decoding():
    """Test that valid access and refresh tokens are created and decoded properly."""
    user_data = {"sub": "user_1", "address": "0x1234", "roles": ["admin"]}
    
    # 1. Access Token
    access_token = auth.create_access_token(user_data)
    decoded_access = auth.decode_token(access_token)
    assert decoded_access["sub"] == "user_1"
    assert decoded_access["type"] == "access"
    assert "jti" in decoded_access
    
    # 2. Refresh Token
    refresh_token = auth.create_refresh_token(user_data)
    decoded_refresh = auth.decode_token(refresh_token)
    assert decoded_refresh["sub"] == "user_1"
    assert decoded_refresh["type"] == "refresh"
    assert "jti" in decoded_refresh


def test_reject_algorithm_none():
    """Test that tokens signed with the 'none' algorithm are explicitly rejected."""
    payload = {
        "sub": "user_1",
        "address": "0x1234",
        "type": "access",
        "jti": "some-jti-uuid",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }
    # Create a token with 'none' algorithm
    unsigned_token = jwt.encode(payload, key="", algorithm="none")
    
    # Check that decode_token raises HTTPException (status 401)
    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(unsigned_token)
    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


def test_token_revocation():
    """Test that token revocation invalidates the token."""
    user_data = {"sub": "user_2", "address": "0x5678", "roles": []}
    access_token = auth.create_access_token(user_data)
    
    # Verify it decodes initially
    payload = auth.decode_token(access_token)
    jti = payload["jti"]
    assert not auth.revocation_store.is_revoked(jti)
    
    # Revoke token
    success = auth.revoke_token(access_token)
    assert success is True
    
    # Verify it is marked as revoked
    assert auth.revocation_store.is_revoked(jti)
    
    # Decoding now should raise HTTPException (401)
    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(access_token)
    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()


def test_refresh_endpoint():
    """Test the POST /auth/refresh endpoint."""
    user_data = {"sub": "user_3", "address": "0x9abc", "roles": ["user"]}
    login_tokens = auth.generate_login_tokens(user_data["sub"], user_data["address"], user_data["roles"])
    refresh_token = login_tokens["refresh_token"]
    
    # Call refresh endpoint
    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    res_data = response.json()
    assert "token" in res_data
    assert "refresh_token" in res_data
    
    # Verify old refresh token is now revoked
    old_payload = jwt.decode(refresh_token, auth.JWT_SECRET, algorithms=[auth.JWT_ALGORITHM])
    assert auth.revocation_store.is_revoked(old_payload["jti"])
    
    # Verify new access token is valid
    new_access_payload = auth.decode_token(res_data["token"])
    assert new_access_payload["sub"] == "user_3"


def test_revoke_endpoint():
    """Test the POST /auth/revoke endpoint."""
    user_data = {"sub": "user_4", "address": "0xdef0", "roles": []}
    access_token = auth.create_access_token(user_data)
    
    # Revoke via body request
    response = client.post("/auth/revoke", json={"token": access_token})
    assert response.status_code == 200
    assert response.json()["message"] == "Token revoked successfully"
    
    # Verify token is indeed revoked
    with pytest.raises(HTTPException):
        auth.decode_token(access_token)
        
    # Create another token and revoke via Authorization header
    access_token_2 = auth.create_access_token(user_data)
    headers = {"Authorization": f"Bearer {access_token_2}"}
    response = client.post("/auth/revoke", headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Token revoked successfully"
    
    # Verify token 2 is revoked
    with pytest.raises(HTTPException):
        auth.decode_token(access_token_2)


def test_production_fallback_check(monkeypatch):
    """Test that missing JWT_SECRET triggers a RuntimeError on startup in production."""
    import importlib
    import sys
    
    # Remove auth from sys.modules to force reload
    if "api.middleware.auth" in sys.modules:
        del sys.modules["api.middleware.auth"]
        
    # Simulate production environment with missing JWT_SECRET
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("ENV", "production")
    
    with pytest.raises(RuntimeError) as exc_info:
        importlib.import_module("api.middleware.auth")
    assert "JWT_SECRET environment variable is missing" in str(exc_info.value)
    
    # Clean up and reload with the correct environment for other tests
    monkeypatch.undo()
    if "api.middleware.auth" in sys.modules:
        del sys.modules["api.middleware.auth"]
    importlib.import_module("api.middleware.auth")
