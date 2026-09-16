"""
Shared security module for the Production-Grade Multi-Project Engineering Ecosystem.
Provides robust password hashing (bcrypt), JWT generation/validation, and secret masking.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import os
import secrets
import bcrypt
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-production-grade-key-change-in-prod-2026")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt with automatic salt generation."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT access token containing subject, role, and expiration."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"iat": now, "exp": expire, "token_type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT refresh token with longer TTL."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"iat": now, "exp": expire, "token_type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a signed JWT token, raising jwt exceptions if expired/invalid."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def generate_secure_api_key(prefix: str = "ll_live") -> str:
    """Generate a secure cryptographic API key."""
    random_bytes = secrets.token_urlsafe(32)
    return f"{prefix}_{random_bytes}"


def mask_secret(secret: str, visible_chars: int = 4) -> str:
    """Mask sensitive string, showing only the last N characters."""
    if not secret or len(secret) <= visible_chars:
        return "****"
    return f"{'*' * (len(secret) - visible_chars)}{secret[-visible_chars:]}"
