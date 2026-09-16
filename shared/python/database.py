"""
Shared database models and engine configuration.
Compatible with SQLite (for instant local zero-dependency verification)
and PostgreSQL / TimescaleDB for production containers.
"""

from datetime import datetime, timezone
import os
from typing import Generator
from sqlalchemy import Boolean, Column, DateTime, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()


class TimestampMixin:
    """Provides created_at and updated_at timestamps in UTC."""
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SoftDeleteMixin:
    """Provides soft-delete capability to prevent unintentional data destruction."""
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)


class AuditMixin:
    """Tracks identity of who created/modified the record."""
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)


def get_db_engine(db_url: str = None, service_name: str = "app"):
    """Creates a configured SQLAlchemy Engine."""
    if not db_url:
        default_sqlite = f"sqlite:///./{service_name}.db"
        db_url = os.getenv("DATABASE_URL", default_sqlite)

    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    return engine


def create_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
