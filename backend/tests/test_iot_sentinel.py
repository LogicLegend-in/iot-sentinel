"""
Automated unit and integration test suite for IoT Sentinel.
Tests device registration, telemetry ingestion, anomaly algorithms (Rule, Z-Score, Isolation Forest),
and alert acknowledgement.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from shared.python.database import Base
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.main import app
from app.api.routes import get_db
from app.models.schemas import (
    AlertRecord,
    AlertStatus,
    AnomalyRecord,
    DetectionRule,
    Device,
    DeviceType,
)
from app.services.anomaly_engine import AnomalyEngine

from sqlalchemy.pool import StaticPool

# In-memory test database with StaticPool
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    # Seed a test device and detection rule
    dev = Device(
        id="test-temp-dev-01",
        name="Test Thermometer Lab A",
        device_type="temperature",
        campus_id="main-campus",
        floor=1,
        room="Lab 101",
        status="online",
        battery_level=90.0,
        signal_strength_rssi=-50,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(dev)

    rule = DetectionRule(
        name="High Temp Alert",
        metric_type="temperature",
        operator=">",
        threshold_value=40.0,
        severity="critical",
        is_active=True,
    )
    db.add(rule)
    db.commit()
    yield
    db.close()
    Base.metadata.drop_all(bind=test_engine)


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "iot-sentinel"


def test_register_device():
    client = TestClient(app)
    payload = {
        "id": "new-sensor-999",
        "name": "Library HVAC Pressure Monitor",
        "device_type": "hvac",
        "campus_id": "main-campus",
        "floor": 2,
        "room": "Room 205",
        "zone": "Library Zone",
        "firmware_version": "v1.0.0",
    }
    response = client.post("/api/v1/iot/devices", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "new-sensor-999"
    assert data["name"] == "Library HVAC Pressure Monitor"


def test_rule_based_anomaly_detection():
    client = TestClient(app)
    # Ingest a temperature reading of 45.0°C which violates the > 40.0°C rule
    telemetry_payload = {
        "device_id": "test-temp-dev-01",
        "metric_type": "temperature",
        "value": 45.5,
        "unit": "°C",
        "battery_level": 88.0,
        "signal_strength_rssi": -52,
    }
    response = client.post("/api/v1/iot/telemetry/ingest", json=telemetry_payload)
    assert response.status_code == 202
    data = response.json()
    assert data["has_anomaly"] is True
    assert data["anomaly"]["method"] == "rule_based"
    assert "High Temp Alert" in data["anomaly"]["explanation"]

    # Verify Alert was created
    alerts_resp = client.get("/api/v1/iot/alerts")
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    assert len(alerts) >= 1
    assert alerts[0]["device_id"] == "test-temp-dev-01"


def test_statistical_zscore_anomaly():
    engine = AnomalyEngine(rolling_window_size=50)
    dev = Device(id="stat-dev-01", name="Stat Device", device_type="temperature", battery_level=90.0)

    # Establish tight baseline history around 20.0
    for _ in range(30):
        engine.evaluate(dev, "temperature", 20.0)

    # Now inject a sudden spike to 38.0 (+18 deviation with zero variance)
    result = engine.evaluate(dev, "temperature", 38.0)
    assert result is not None
    anomaly, alert = result
    assert anomaly.method == "statistical"
    assert "Statistical Outlier" in anomaly.explanation
    assert anomaly.anomaly_score >= 0.8


def test_isolation_forest_anomaly():
    engine = AnomalyEngine(rolling_window_size=50)
    dev = Device(id="ml-dev-01", name="ML Device", device_type="energy_meter", battery_level=95.0)

    # Train sliding window with normal varied distribution
    import random
    random.seed(42)
    for _ in range(35):
        val = 15.0 + random.uniform(-1.0, 1.0)
        engine.evaluate(dev, "energy_meter", val)

    # Inject extreme multivariate surge
    result = engine.evaluate(dev, "energy_meter", 75.0)
    assert result is not None
    anomaly, alert = result
    assert anomaly.method in ["statistical", "isolation_forest"]
    assert anomaly.severity in ["critical", "high"]


def test_alert_acknowledgement():
    client = TestClient(app)
    # Trigger an alert first
    client.post("/api/v1/iot/telemetry/ingest", json={
        "device_id": "test-temp-dev-01",
        "metric_type": "temperature",
        "value": 50.0,
        "unit": "°C",
    })

    alerts = client.get("/api/v1/iot/alerts").json()
    assert len(alerts) > 0
    alert_id = alerts[0]["id"]

    # Acknowledge
    ack_resp = client.post(f"/api/v1/iot/alerts/{alert_id}/acknowledge", json={
        "acknowledged_by": "engineer@campus.edu",
    })
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == AlertStatus.ACKNOWLEDGED.value
    assert ack_resp.json()["acknowledged_by"] == "engineer@campus.edu"
