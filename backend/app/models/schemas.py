"""
Database models and Pydantic schemas for IoT Sentinel.
Handles Campuses, Buildings, Devices, Telemetry, Anomaly Detection, Alerts, Maintenance, and Audit Logs.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

from shared.python.database import Base, TimestampMixin, SoftDeleteMixin


# -------------------------------------------------------------
# Enums
# -------------------------------------------------------------
class DeviceType(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    ENERGY_METER = "energy_meter"
    AIR_QUALITY = "air_quality"
    OCCUPANCY = "occupancy"
    WATER_LEVEL = "water_level"
    SMART_LIGHTING = "smart_lighting"
    HVAC = "hvac"


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    ERROR = "error"


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AnomalyMethod(str, Enum):
    RULE_BASED = "rule_based"
    STATISTICAL = "statistical"
    ISOLATION_FOREST = "isolation_forest"


# -------------------------------------------------------------
# SQLAlchemy Database Models
# -------------------------------------------------------------
class Campus(Base, TimestampMixin):
    __tablename__ = "campuses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False)
    location = Column(String(255), nullable=True)
    description = Column(String(255), nullable=True)

    buildings = relationship("Building", back_populates="campus", cascade="all, delete-orphan")


class Building(Base, TimestampMixin):
    __tablename__ = "buildings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campus_id = Column(String(36), ForeignKey("campuses.id"), nullable=False)
    name = Column(String(120), nullable=False)
    floors_count = Column(Integer, default=4)

    campus = relationship("Campus", back_populates="buildings")
    devices = relationship("Device", back_populates="building")


class Device(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "devices"

    id = Column(String(64), primary_key=True)
    name = Column(String(120), nullable=False)
    device_type = Column(String(32), nullable=False, index=True)
    campus_id = Column(String(36), nullable=False, index=True)
    building_id = Column(String(36), ForeignKey("buildings.id"), nullable=True)
    floor = Column(Integer, default=1)
    room = Column(String(64), nullable=True)
    zone = Column(String(64), default="General Zone")

    status = Column(String(32), default=DeviceStatus.ONLINE.value, index=True)
    ip_address = Column(String(64), nullable=True)
    mac_address = Column(String(32), nullable=True)
    firmware_version = Column(String(32), default="v2.4.1")
    battery_level = Column(Float, default=95.0)
    signal_strength_rssi = Column(Integer, default=-55)
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    secret_hash = Column(String(255), nullable=True)

    building = relationship("Building", back_populates="devices")
    telemetry = relationship("TelemetryRecord", back_populates="device", cascade="all, delete-orphan")
    anomalies = relationship("AnomalyRecord", back_populates="device", cascade="all, delete-orphan")


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    metric_type = Column(String(32), nullable=False, index=True)
    value = Column(Float, nullable=False)
    unit = Column(String(16), nullable=False)
    raw_payload = Column(Text, nullable=True)

    device = relationship("Device", back_populates="telemetry")


class AnomalyRecord(Base):
    __tablename__ = "anomaly_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    metric = Column(String(32), nullable=False)
    value = Column(Float, nullable=False)
    anomaly_score = Column(Float, nullable=False)
    severity = Column(String(16), nullable=False)
    method = Column(String(32), nullable=False)
    explanation = Column(Text, nullable=False)
    status = Column(String(32), default=AlertStatus.OPEN.value)

    device = relationship("Device", back_populates="anomalies")


class AlertRecord(Base, TimestampMixin):
    __tablename__ = "alert_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=False, index=True)
    anomaly_id = Column(String(36), nullable=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(16), default=AlertSeverity.HIGH.value, index=True)
    status = Column(String(32), default=AlertStatus.OPEN.value, index=True)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)


class MaintenanceTicket(Base, TimestampMixin):
    __tablename__ = "maintenance_tickets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=False)
    alert_id = Column(String(36), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(16), default="HIGH")
    status = Column(String(32), default="PENDING")
    assigned_to = Column(String(100), default="Campus Facilities Engineering")


class DetectionRule(Base, TimestampMixin):
    __tablename__ = "detection_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False)
    metric_type = Column(String(32), nullable=False)
    operator = Column(String(8), nullable=False)  # >, <, >=, <=, ==
    threshold_value = Column(Float, nullable=False)
    severity = Column(String(16), default=AlertSeverity.HIGH.value)
    is_active = Column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    user_email = Column(String(120), nullable=False)
    action = Column(String(64), nullable=False)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(120), nullable=True)
    details = Column(Text, nullable=True)


# -------------------------------------------------------------
# Pydantic Schemas for API Requests & Responses
# -------------------------------------------------------------
from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    id: str = Field(..., json_schema_extra={"example": "sen-temp-eng-101"})
    name: str = Field(..., json_schema_extra={"example": "Engineering Lab Thermometer A"})
    device_type: DeviceType
    campus_id: str = "main-campus"
    building_id: Optional[str] = None
    floor: int = 1
    room: Optional[str] = "Lab 101"
    zone: str = "Academic Zone"
    firmware_version: str = "v2.4.1"


class TelemetryIngest(BaseModel):
    device_id: str
    metric_type: str
    value: float
    unit: str
    timestamp: Optional[datetime] = None
    battery_level: Optional[float] = None
    signal_strength_rssi: Optional[int] = None


class AnomalyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    metric: str
    timestamp: datetime
    value: float
    anomaly_score: float
    severity: str
    method: str
    explanation: str
    status: str


class AlertAcknowledgeRequest(BaseModel):
    acknowledged_by: str = "admin@campus.edu"


class MaintenanceTicketCreate(BaseModel):
    device_id: str
    alert_id: Optional[str] = None
    title: str
    description: str
    priority: str = "HIGH"
    assigned_to: str = "Campus Facilities Engineering"
