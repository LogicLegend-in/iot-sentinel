"""
Shared authentication and Role-Based Access Control (RBAC) dependencies.
Supports roles: ADMIN, MAINTAINER, CONTRIBUTOR, VIEWER.
"""

from enum import Enum
from typing import List, Optional
from fastapi import Depends, HTTPException, Header, status
from pydantic import BaseModel, EmailStr
import jwt

from shared.python.security import decode_token


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    MAINTAINER = "MAINTAINER"
    CONTRIBUTOR = "CONTRIBUTOR"
    VIEWER = "VIEWER"


# Role hierarchy score for permission escalation/checks
ROLE_HIERARCHY = {
    UserRole.VIEWER: 1,
    UserRole.CONTRIBUTOR: 2,
    UserRole.MAINTAINER: 3,
    UserRole.ADMIN: 4,
}


class TokenPayload(BaseModel):
    sub: str  # user_id
    email: str
    role: UserRole
    name: Optional[str] = None
    exp: Optional[int] = None


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole
    is_active: bool = True


async def get_current_user(authorization: Optional[str] = Header(None)) -> AuthenticatedUser:
    """Dependency to extract and validate the JWT Bearer token from the Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        email = payload.get("email")
        role_str = payload.get("role", "VIEWER")
        name = payload.get("name", "Demo User")

        if not user_id or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing required claims",
            )

        role = UserRole(role_str) if role_str in UserRole.__members__ else UserRole.VIEWER
        return AuthenticatedUser(id=user_id, email=email, name=name, role=role)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please refresh your session.",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )


def require_role(minimum_role: UserRole):
    """FastAPI dependency generator requiring a minimum role rank in the RBAC hierarchy."""
    async def role_checker(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = ROLE_HIERARCHY.get(minimum_role, 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires minimum role {minimum_role.value}, but you have {current_user.role.value}",
            )
        return current_user

    return role_checker
