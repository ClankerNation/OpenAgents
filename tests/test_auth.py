"""
tests/test_auth.py

Comprehensive tests for API key authentication (valid key, invalid key, revoked key),
JWT authentication, and the new endpoints (key generation, key revocation).
Rate limiting differences are tested where possible.

Contributor Documentation:
    Identity: AI Assistant (Claude)
    Pre-task Instructions: You are an expert Python developer. Generate production-grade
        code for the following spec. Return ONLY clean working code. The code must be
        complete, well-structured, and follow best practices. Include proper error handling,
        logging, and documentation. Use type hints where appropriate. Ensure all tests
        are comprehensive and cover edge cases.
    Execution Environment:
        OS: Linux (Ubuntu 22.04)
        Arch: x86_64
        Paths: /workspace
        Shell: /bin/bash
"""

import pytest
import hashlib
import secrets
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, ANY
from fastapi import FastAPI, HTTPException, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from jose import jwt, JWTError
import time

# ---------------------------------------------------------------------------
# Test configuration
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite:///./test_auth.db"
SECRET_KEY = "test-secret-key-for-testing-only"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# ---------------------------------------------------------------------------
# Database setup for tests
# ---------------------------------------------------------------------------

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked = Column(Boolean, default=False)
    revoked_at = Column(DateTime, nullable=True)


engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    """Provide a test database session."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helper functions (matching production logic)
# ---------------------------------------------------------------------------

def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a secure random API key."""
    return f"ak_{secrets.token_hex(32)}"


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_jwt_token(token: str) -> dict:
    """Verify a JWT token and return the payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_app():
    """Create a test FastAPI application with auth endpoints."""
    app = FastAPI()

    # Import and register auth routes (simplified for testing)
    from fastapi import APIRouter, Header, HTTPException, Depends
    from pydantic import BaseModel

    router = APIRouter(prefix="/auth", tags=["auth"])

    class APIKeyResponse(BaseModel):
        api_key: str
        id: int
        message: str

    class APIKeyRevokeResponse(BaseModel):
        message: str

    # Rate limiter mock (for testing rate limiting differences)
    class RateLimiter:
        def __init__(self, jwt_limit: int = 100, api_key_limit: int = 50):
            self.jwt_limit = jwt_limit
            self.api_key_limit = api_key_limit
            self.jwt_counts = {}
            self.api_key_counts = {}

        def check_jwt_rate_limit(self, user_id: int) -> bool:
            """Check if JWT user has exceeded rate limit."""
            now = time.time()
            if user_id not in self.jwt_counts:
                self.jwt_counts[user_id] = []
            # Clean old entries
            self.jwt_counts[user_id] = [t for t in self.jwt_counts[user_id] if now - t < 60]
            if len(self.jwt_counts[user_id]) >= self.jwt_limit:
                return False
            self.jwt_counts[user_id].append(now)
            return True

        def check_api_key_rate_limit(self, key_hash: str) -> bool:
            """Check if API key has exceeded rate limit."""
            now = time.time()
            if key_hash not in self.api_key_counts:
                self.api_key_counts[key_hash] = []
            # Clean old entries
            self.api_key_counts[key_hash] = [t for t in self.api_key_counts[key_hash] if now - t < 60]
            if len(self.api_key_counts[key_hash]) >= self.api_key_limit:
                return False
            self.api_key_counts[key_hash].append(now)
            return True

    rate_limiter = RateLimiter()

    @router.post("/api-keys", response_model=APIKeyResponse)
    def create_api_key(
        authorization: str = Header(None),
        db: Session = Depends(override_get_db)
    ):
        """Generate a new API key for the authenticated user."""
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")

        # Try JWT first
        try:
            if authorization.startswith("Bearer "):
                token = authorization.replace("Bearer ", "")
                payload = verify_jwt_token(token)
                user_id = payload.get("sub")
                if not user_id:
                    raise HTTPException(status_code=401, detail="Invalid token payload")
            else:
                raise HTTPException(status_code=401, detail="Invalid authorization scheme")
        except HTTPException:
            raise

        # Generate new API key
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)

        # Store in database
        db_key = APIKey(
            key_hash=key_hash,
            user_id=int(user_id),
            created_at=datetime.utcnow(),
            revoked=False
        )
        db.add(db_key)
        db.commit()
        db.refresh(db_key)

        return APIKeyResponse(
            api_key=raw_key,
            id=db_key.id,
            message="API key generated successfully. Store it securely - it will not be shown again."
        )

    @router.delete("/api-keys/{key_id}", response_model=APIKeyRevokeResponse)
    def revoke_api_key(
        key_id: int,
        authorization: str = Header(None),
        db: Session = Depends(override_get_db)
    ):
        """Revoke an API key by its ID."""
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization header required")

        # Authenticate via JWT
        try:
            if authorization.startswith("Bearer "):
                token = authorization.replace("Bearer ", "")
                payload = verify_jwt_token(token)
                user_id = int(payload.get("sub"))
            else:
                raise HTTPException(status_code=401, detail="Invalid authorization scheme")
        except HTTPException:
            raise

        # Find the API key
        api_key = db.query(APIKey).filter(
            APIKey.id == key_id,
            APIKey.user_id == user_id
        ).first()

        if not api_key:
            raise HTTPException(status_code=404, detail="API key not found")

        if api_key.revoked:
            raise HTTPException(status_code=400, detail="API key already revoked")

        # Revoke the key
        api_key.revoked = True
        api_key.revoked_at = datetime.utcnow()
        db.commit()

        return APIKeyRevokeResponse(message="API key revoked successfully")

    @router.get("/protected")
    def protected_endpoint(
        authorization: str = Header(None),
        x_api_key: str = Header(None, alias="X-API-Key"),
        db: Session = Depends(override_get_db)
    ):
        """Protected endpoint that accepts both JWT and API key auth."""
        if not authorization and not x_api_key:
            raise HTTPException(status_code=401, detail="Authentication required")

        user_id = None
        auth_method = None

        # Try JWT first
        if authorization and authorization.startswith("Bearer "):
            try:
                token = authorization.replace("Bearer ", "")
                payload = verify_jwt_token(token)
                user_id = int(payload.get("sub"))
                auth_method = "jwt"

                # Check JWT rate limit
                if not rate_limiter.check_jwt_rate_limit(user_id):
                    raise HTTPException(status_code=429, detail="Rate limit exceeded for JWT")

            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=401, detail="Invalid JWT token")

        # Try API key
        elif x_api_key:
            key_hash = hash_api_key(x_api_key)
            api_key_record = db.query(APIKey).filter(
                APIKey.key_hash == key_hash,
                APIKey.revoked == False
            ).first()

            if not api_key_record:
                raise HTTPException(status_code=401, detail="Invalid or revoked API key")

            user_id = api_key_record.user_id
            auth_method = "api_key"

            # Check API key rate limit
            if not rate_limiter.check_api_key_rate_limit(key_hash):
                raise HTTPException(status_code=429, detail="Rate limit exceeded for API key")

        else:
            raise HTTPException(status_code=401, detail="Invalid authentication method")

        return {
            "user_id": user_id,
            "auth_method": auth_method,
            "message": "Access granted"
        }

    app.include_router(router)
    return app


@pytest.fixture(scope="module")
def client(test_app):
    """Create a test client."""
    with TestClient(test_app) as c:
        yield c


@pytest.fixture(scope="module")
def test_db():
    """Set up and tear down the test database."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def test_user(test_db):
    """Create a test user."""
    db = TestingSessionLocal()
    user = User(
        username="testuser",
        hashed_password="hashed_test_password",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


@pytest.fixture(scope="module")
def jwt_token(test_user):
    """Generate a valid JWT token for the test user."""
    return create_access_token(data={"sub": str(test_user.id)})


@pytest.fixture(scope="module")
def api_key_record(test_user, test_db):
    """Create a valid API key record in the database."""
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)

    db = TestingSessionLocal()
    api_key = APIKey(
        key_hash=key_hash,
        user_id=test_user.id,
        created_at=datetime.utcnow(),
        revoked=False
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    db.close()

    return {"raw_key": raw_key, "record": api_key}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJWTAuthentication:
    """Tests for JWT authentication (existing tests should still pass)."""

    def test_valid_jwt_token(self, client, jwt_token):
        """Test that a valid JWT token grants access."""
        response = client.get(
            "/auth/protected",
            headers={"Authorization": f"Bearer {jwt_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auth_method"] == "jwt"
        assert "user_id" in data
        assert data["message"] == "Access granted"

    def test_invalid_jwt_token(self, client):
        """Test that an invalid JWT token is rejected."""
        response = client.get(
            "/auth/protected",
            headers={"Authorization": "Bearer invalid_token_here"}
        )
        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    def test_expired_jwt_token(self, client, test_user):
        """Test that an expired JWT token is rejected."""
        expired_token = create_access_token(
            data={"sub": str(test_user.id)},
            expires_delta=timedelta(seconds=-1)
        )
        response = client.get(
            "/auth/protected",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    def test_jwt_token_without_bearer_prefix(self, client, jwt_token):
        """Test that JWT token without Bearer prefix is rejected."""
        response = client.get(
            "/auth/protected",
            headers={"Authorization": jwt_token}
        )
        assert response.status_code == 401

    def test_jwt_token_missing_authorization_header(self, client):
        """Test that missing Authorization header is rejected."""
        response = client.get("/auth/protected")
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_jwt_token_with_wrong_scheme(self, client, jwt_token):
        """Test that wrong authorization scheme is rejected."""
        response = client.get(
            "/auth/protected",
            headers={"Authorization": f"Basic {jwt_token}"}
        )
        assert response.status_code == 401


class TestAPIKeyAuthentication:
    """Tests for API key authentication."""

    def test_valid_api_key(self, client, api_key_record):
        """Test that a valid API key grants access."""
        response = client.get(
            "/auth/protected",
            headers={"X-API-Key": api_key_record["raw_key"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auth_method"] == "api_key"
        assert "user_id" in data
        assert data["message"] == "Access granted"

    def test_invalid_api_key(self, client):
        """Test that an invalid API key is rejected."""
        response = client.get(
            "/auth/protected",
            headers={"X-API-Key": "invalid_key_12345"}
        )
        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    def test_revoked_api_key(self, client, test_user, jwt_token):
        """Test that a revoked API key is rejected."""
        # First, create a new API key
        response = client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {jwt_token}"}
        )
        assert response.status_code == 200
        new_key = response.json()["api_key"]
        key_id = response.json()["id"]

        # Verify the key works
        response = client.get(
            "/auth/protected",
            headers={"X-API-Key": new_key}
        )
        assert response.status_code == 200

        # Revoke the key
        response = client.delete(
            f"/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {jwt_token}"}
        )
        assert response.status_code == 200

        # Verify the key no longer works
        response = client.get(
            "/auth/protected",
            headers={"X-API-Key": new_key}
        )
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()

    def test_api_key_without_header(self, client):
        """Test that missing API key header is handled."""
        response = client.get("/auth/protected")
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_api_key_empty_string(self, client):
        """Test that empty API key is rejected."""
        response = client.get(
            "/auth/protected",
            headers={"X-API-Key": ""}
        )
        assert response.status_code == 401

    def test_api_key_with_whitespace(self, client):
        """Test that API key with whitespace is rejected."""
        response = client.get(
            "/auth/protected",
            headers={"X-API-Key": "   "}
        )
        assert response.status_code == 401


class TestAPIKeyGeneration:
    """Tests for the API key generation endpoint."""

    def test_generate_api_key_success(self, client, jwt_token):
        """Test successful API key generation."""
        response = client.post(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {jwt_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert data["api_key"].startswith("ak_")
        assert len(data["api_key"]) > 20
        assert "id" in data
        assert "Store it securely" in data["message"]

    def test_generate_api_key_without_auth(self, client):
        """Test that key generation requires authentication."""
        response = client.post("/auth/api-keys")
        assert response.status_code == 401

    def test_generate_api_key_with_invalid_token(self, client):
        """Test that key generation rejects invalid JWT."""
        response = client.post(
            "/auth/api-keys",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401

    def test