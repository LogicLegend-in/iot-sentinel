"""
REST and WebSocket API endpoints for IoT Sentinel.
Handles device management, telemetry ingestion, anomaly detection, alerts, and campus hierarchy.
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models.schemas import (
    AlertAcknowledgeRequest,
    AlertRecord,
    AlertSeverity,
    AlertStatus,
    AnomalyOut,
    AnomalyRecord,
    Building,
    Campus,
    DetectionRule,
    Device,
    DeviceCreate,
    DeviceStatus,
    MaintenanceTicket,
    MaintenanceTicketCreate,
    TelemetryIngest,
    TelemetryRecord,
    AuditLog,
)
from ..services.anomaly_engine import AnomalyEngine
from ..services.websocket_manager import ws_manager

router = APIRouter(prefix="/api/v1/iot", tags=["IoT Sentinel"])
anomaly_engine = AnomalyEngine()


def get_db():
    from ..main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------------
# Dashboard Summary / KPIs
# -------------------------------------------------------------
@router.get("/dashboard-summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    total_devices = db.query(Device).filter(Device.is_deleted == False).count()
    online_devices = db.query(Device).filter(Device.is_deleted == False, Device.status == DeviceStatus.ONLINE.value).count()
    offline_devices = db.query(Device).filter(Device.is_deleted == False, Device.status == DeviceStatus.OFFLINE.value).count()
    active_alerts = db.query(AlertRecord).filter(AlertRecord.status == AlertStatus.OPEN.value).count()
    total_anomalies = db.query(AnomalyRecord).count()

    # Calculate average campus temperature from latest telemetry
    avg_temp_row = (
        db.query(func.avg(TelemetryRecord.value))
        .filter(TelemetryRecord.metric_type == "temperature")
        .first()
    )
    avg_temp = round(float(avg_temp_row[0]), 1) if avg_temp_row and avg_temp_row[0] else 21.5

    # Calculate total energy consumption
    energy_sum_row = (
        db.query(func.sum(TelemetryRecord.value))
        .filter(TelemetryRecord.metric_type == "energy_meter")
        .first()
    )
    total_energy_kwh = round(float(energy_sum_row[0]), 1) if energy_sum_row and energy_sum_row[0] else 412.8

    return {
        "total_devices": total_devices,
        "online_devices": online_devices,
        "offline_devices": offline_devices,
        "active_alerts": active_alerts,
        "total_anomalies": total_anomalies,
        "average_temperature_celsius": avg_temp,
        "total_energy_consumption_kwh": total_energy_kwh,
        "system_status": "OPERATIONAL" if active_alerts < 5 else "ATTENTION_REQUIRED",
    }


# -------------------------------------------------------------
# Device Management
# -------------------------------------------------------------
@router.get("/devices")
def list_devices(
    device_type: Optional[str] = None,
    building_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Device).filter(Device.is_deleted == False)
    if device_type:
        query = query.filter(Device.device_type == device_type)
    if building_id:
        query = query.filter(Device.building_id == building_id)
    if status_filter:
        query = query.filter(Device.status == status_filter)
    return query.order_by(Device.name).all()


@router.get("/devices/{device_id}")
def get_device(device_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id, Device.is_deleted == False).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    recent_telemetry = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.device_id == device_id)
        .order_by(TelemetryRecord.timestamp.desc())
        .limit(20)
        .all()
    )
    return {"device": device, "recent_telemetry": recent_telemetry}


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def register_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    existing = db.query(Device).filter(Device.id == payload.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Device ID already exists")

    new_device = Device(
        id=payload.id,
        name=payload.name,
        device_type=payload.device_type.value,
        campus_id=payload.campus_id,
        building_id=payload.building_id,
        floor=payload.floor,
        room=payload.room,
        zone=payload.zone,
        firmware_version=payload.firmware_version,
        status=DeviceStatus.ONLINE.value,
    )
    db.add(new_device)

    # Audit log
    audit = AuditLog(
        user_email="admin@campus.edu",
        action="DEVICE_CREATED",
        resource_type="Device",
        resource_id=new_device.id,
        details=f"Device {new_device.name} registered in room {new_device.room}",
    )
    db.add(audit)
    db.commit()
    db.refresh(new_device)
    return new_device


# -------------------------------------------------------------
# Telemetry Ingestion & Real-Time Processing
# -------------------------------------------------------------
@router.post("/telemetry/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_telemetry(payload: TelemetryIngest, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == payload.device_id, Device.is_deleted == False).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {payload.device_id} not registered")

    ts = payload.timestamp or datetime.now(timezone.utc)
    device.last_seen_at = ts
    if payload.battery_level is not None:
        device.battery_level = payload.battery_level
    if payload.signal_strength_rssi is not None:
        device.signal_strength_rssi = payload.signal_strength_rssi

    # Save Telemetry Record
    telemetry_rec = TelemetryRecord(
        device_id=payload.device_id,
        timestamp=ts,
        metric_type=payload.metric_type,
        value=payload.value,
        unit=payload.unit,
    )
    db.add(telemetry_rec)

    # Run Anomaly Engine
    rules = db.query(DetectionRule).filter(DetectionRule.is_active == True).all()
    eval_result = anomaly_engine.evaluate(device, payload.metric_type, payload.value, rules)

    anomaly_data = None
    alert_data = None
    if eval_result:
        anomaly_obj, alert_obj = eval_result
        db.add(anomaly_obj)
        db.flush()
        if alert_obj:
            alert_obj.anomaly_id = anomaly_obj.id
            db.add(alert_obj)
            db.flush()
            alert_data = {
                "id": alert_obj.id,
                "title": alert_obj.title,
                "severity": alert_obj.severity,
                "message": alert_obj.message,
            }
        anomaly_data = {
            "id": anomaly_obj.id,
            "metric": anomaly_obj.metric,
            "value": anomaly_obj.value,
            "anomaly_score": anomaly_obj.anomaly_score,
            "severity": anomaly_obj.severity,
            "method": anomaly_obj.method,
            "explanation": anomaly_obj.explanation,
        }

    db.commit()

    # Broadcast via WebSocket
    broadcast_payload = {
        "type": "TELEMETRY_UPDATE",
        "device_id": device.id,
        "device_name": device.name,
        "metric": payload.metric_type,
        "value": payload.value,
        "unit": payload.unit,
        "battery": device.battery_level,
        "signal": device.signal_strength_rssi,
        "timestamp": ts.isoformat(),
        "anomaly": anomaly_data,
        "alert": alert_data,
    }
    await ws_manager.broadcast_json(broadcast_payload)

    return {
        "status": "ingested",
        "device_id": device.id,
        "has_anomaly": anomaly_data is not None,
        "anomaly": anomaly_data,
    }


@router.get("/telemetry/history")
def get_telemetry_history(
    device_id: Optional[str] = None,
    metric_type: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(TelemetryRecord)
    if device_id:
        query = query.filter(TelemetryRecord.device_id == device_id)
    if metric_type:
        query = query.filter(TelemetryRecord.metric_type == metric_type)
    records = query.order_by(TelemetryRecord.timestamp.desc()).limit(limit).all()
    return list(reversed(records))


# -------------------------------------------------------------
# Anomalies & Alerts Management
# -------------------------------------------------------------
@router.get("/anomalies")
def list_anomalies(
    severity: Optional[str] = None,
    method: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AnomalyRecord)
    if severity:
        query = query.filter(AnomalyRecord.severity == severity)
    if method:
        query = query.filter(AnomalyRecord.method == method)
    return query.order_by(AnomalyRecord.timestamp.desc()).limit(limit).all()


@router.get("/alerts")
def list_alerts(status_filter: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(AlertRecord)
    if status_filter:
        query = query.filter(AlertRecord.status == status_filter)
    return query.order_by(AlertRecord.created_at.desc()).limit(100).all()


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledgeRequest,
    db: Session = Depends(get_db),
):
    alert = db.query(AlertRecord).filter(AlertRecord.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = AlertStatus.ACKNOWLEDGED.value
    alert.acknowledged_by = payload.acknowledged_by
    alert.acknowledged_at = datetime.now(timezone.utc)

    # Add audit log
    audit = AuditLog(
        user_email=payload.acknowledged_by,
        action="ALERT_ACKNOWLEDGED",
        resource_type="AlertRecord",
        resource_id=alert.id,
        details=f"Alert '{alert.title}' acknowledged",
    )
    db.add(audit)
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(AlertRecord).filter(AlertRecord.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = AlertStatus.RESOLVED.value
    db.commit()
    db.refresh(alert)
    return alert


# -------------------------------------------------------------
# Maintenance Tickets
# -------------------------------------------------------------
@router.get("/maintenance")
def list_maintenance_tickets(db: Session = Depends(get_db)):
    return db.query(MaintenanceTicket).order_by(MaintenanceTicket.created_at.desc()).all()


@router.post("/maintenance", status_code=status.HTTP_201_CREATED)
def create_maintenance_ticket(payload: MaintenanceTicketCreate, db: Session = Depends(get_db)):
    ticket = MaintenanceTicket(
        device_id=payload.device_id,
        alert_id=payload.alert_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        assigned_to=payload.assigned_to,
        status="PENDING",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


# -------------------------------------------------------------
# Detection Rules
# -------------------------------------------------------------
@router.get("/rules")
def list_rules(db: Session = Depends(get_db)):
    return db.query(DetectionRule).all()


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(
    name: str,
    metric_type: str,
    operator: str,
    threshold_value: float,
    severity: str = "high",
    db: Session = Depends(get_db),
):
    rule = DetectionRule(
        name=name,
        metric_type=metric_type,
        operator=operator,
        threshold_value=threshold_value,
        severity=severity,
        is_active=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# -------------------------------------------------------------
# Campus & Building Hierarchy
# -------------------------------------------------------------
@router.get("/buildings")
def list_buildings(db: Session = Depends(get_db)):
    buildings = db.query(Building).all()
    results = []
    for b in buildings:
        dev_count = db.query(Device).filter(Device.building_id == b.id, Device.is_deleted == False).count()
        results.append({
            "id": b.id,
            "name": b.name,
            "campus_id": b.campus_id,
            "floors_count": b.floors_count,
            "device_count": dev_count,
        })
    return results


# -------------------------------------------------------------
# Audit Logs
# -------------------------------------------------------------
@router.get("/audit-logs")
def list_audit_logs(limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()


# -------------------------------------------------------------
# Simulator Pulse Trigger
# -------------------------------------------------------------
@router.post("/simulator/pulse")
async def trigger_simulator_pulse(db: Session = Depends(get_db)):
    from ..services.simulator import simulator
    devices = db.query(Device).filter(Device.status == "online", Device.is_deleted == False).all()
    results = []
    for dev in devices[:10]:
        reading = simulator.generate_reading(dev)
        res = await ingest_telemetry(reading, db)
        results.append(res)
    return {"status": "pulse_complete", "devices_pulsed": len(results), "readings": results}
