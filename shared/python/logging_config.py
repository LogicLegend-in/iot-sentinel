"""
Production structured JSON logging for the multi-project engineering ecosystem.
Enforces request correlation IDs and redacts secrets, tokens, and passwords.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "authorization",
    "api_key",
    "github_token",
    "private_key",
}


def redact_sensitive_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redacts values for keys known to be sensitive."""
    sanitized = {}
    for k, v in d.items():
        if any(secret_key in k.lower() for secret_key in SENSITIVE_KEYS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = redact_sensitive_dict(v)
        elif isinstance(v, list):
            sanitized[k] = [
                redact_sensitive_dict(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            sanitized[k] = v
    return sanitized


class JsonFormatter(logging.Formatter):
    """Formats log records as one-line JSON documents with standard schema."""

    def __init__(self, service_name: str = "production-service"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", self.service_name),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Merge any extra metadata attached to record
        if hasattr(record, "metadata") and isinstance(record.metadata, dict):
            log_data["metadata"] = redact_sensitive_dict(record.metadata)

        return json.dumps(log_data)


def configure_logger(service_name: str = "production-service", level: int = logging.INFO) -> logging.Logger:
    """Creates or configures a root logger that outputs structured JSON."""
    logger = logging.getLogger(service_name)
    logger.setLevel(level)

    # Avoid duplicate handlers if already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(service_name=service_name))
        logger.addHandler(handler)
        logger.propagate = False

    return logger
