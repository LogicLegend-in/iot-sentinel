"""
Standardized error formatting and exceptions across all platform APIs.
Follows OWASP and enterprise API guidelines with correlation IDs and strict privacy.
"""

from typing import Any, Dict, Optional
import uuid
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    details: Optional[Dict[str, Any]] = None


class StandardErrorResponse(BaseModel):
    error: ErrorDetail


class PlatformException(HTTPException):
    """Base application exception returning standardized JSON responses."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.request_id = request_id or f"req_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "request_id": self.request_id,
                "details": self.details,
            }
        }


def make_error_response(
    status_code: int,
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> JSONResponse:
    """Format and return a standard JSON error response."""
    rid = request_id or f"req_{uuid.uuid4().hex[:12]}"
    payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": rid,
            "details": details or {},
        }
    }
    return JSONResponse(status_code=status_code, content=payload)
