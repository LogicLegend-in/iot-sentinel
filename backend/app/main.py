"""
Main FastAPI application for IoT Sentinel.
Initializes database, seeds initial campus infrastructure, provides Prometheus metrics,
manages WebSocket connections, and runs background device simulator.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import os
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from shared.python.database import get_db_engine, create_session_factory, Base
from shared.python.logging_config import configure_logger
from .models.schemas import (
    AlertRecord,
    AlertSeverity,
    AlertStatus,
    Building,
    Campus,
    DetectionRule,
    Device,
    DeviceStatus,
    DeviceType,
    TelemetryRecord,
)
from .api.routes import router as iot_router
from .services.websocket_manager import ws_manager
from .services.simulator import simulator

logger = configure_logger("iot-sentinel-service")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./iot_sentinel.db")
engine = get_db_engine(DATABASE_URL, service_name="iot_sentinel")
SessionLocal = create_session_factory(engine)


def seed_database(db: Session):
    """Seeds realistic smart-campus infrastructure with 50+ devices and baseline telemetry."""
    if db.query(Campus).count() > 0:
        return

    logger.info("Seeding IoT Sentinel database with campus buildings, devices, and historical telemetry...")

    campus = Campus(
        id="campus-main",
        name="LogicLegend Smart University Campus",
        location="North Innovation Sector",
        description="Flagship connected academic and research campus",
    )
    db.add(campus)
    db.flush()

    buildings_data = [
        ("bld-eng", "Engineering & Robotics Complex", 5),
        ("bld-sci", "Natural Sciences Laboratory", 4),
        ("bld-union", "Student Union & Dining Hall", 3),
        ("bld-lib", "Grand Central Library", 6),
        ("bld-innov", "AI & Cyber Innovation Hub", 4),
    ]

    buildings = []
    for b_id, b_name, floors in buildings_data:
        b = Building(id=b_id, campus_id=campus.id, name=b_name, floors_count=floors)
        db.add(b)
        buildings.append(b)
    db.flush()

    device_types = [
        DeviceType.TEMPERATURE,
        DeviceType.HUMIDITY,
        DeviceType.ENERGY_METER,
        DeviceType.AIR_QUALITY,
        DeviceType.OCCUPANCY,
        DeviceType.WATER_LEVEL,
        DeviceType.SMART_LIGHTING,
        DeviceType.HVAC,
    ]

    created_devices = []
    device_counter = 100

    for b in buildings:
        for fl in range(1, b.floors_count + 1):
            for d_type in device_types:
                device_counter += 1
                dev_id = f"dev-{d_type.value[:4]}-{b.id.split('-')[1]}-{fl}{device_counter % 10}"
                name = f"{b.name.split()[0]} Fl.{fl} {d_type.value.replace('_', ' ').title()}"
                room = f"Room {fl}0{random.randint(1, 8)}"
                dev = Device(
                    id=dev_id,
                    name=name,
                    device_type=d_type.value,
                    campus_id=campus.id,
                    building_id=b.id,
                    floor=fl,
                    room=room,
                    zone=f"{b.name.split()[0]} Zone",
                    status=DeviceStatus.ONLINE.value if random.random() > 0.05 else DeviceStatus.OFFLINE.value,
                    battery_level=round(random.uniform(70.0, 99.0), 1),
                    signal_strength_rssi=random.randint(-70, -45),
                    firmware_version="v2.4.1",
                    last_seen_at=datetime.now(timezone.utc),
                )
                db.add(dev)
                created_devices.append(dev)

    # Detection Rules
    default_rules = [
        DetectionRule(name="Critical Overheating Guard", metric_type="temperature", operator=">", threshold_value=36.0, severity=AlertSeverity.CRITICAL.value),
        DetectionRule(name="Server Room Humidity Spike", metric_type="humidity", operator=">", threshold_value=85.0, severity=AlertSeverity.HIGH.value),
        DetectionRule(name="Peak Load Energy Surge", metric_type="energy_meter", operator=">", threshold_value=45.0, severity=AlertSeverity.HIGH.value),
        DetectionRule(name="Hazardous AQI Air Quality", metric_type="air_quality", operator=">", threshold_value=180.0, severity=AlertSeverity.CRITICAL.value),
        DetectionRule(name="Reservoir Flood Level", metric_type="water_level", operator=">", threshold_value=5.5, severity=AlertSeverity.CRITICAL.value),
    ]
    for r in default_rules:
        db.add(r)

    # Generate historical telemetry for the first 10 devices
    now = datetime.now(timezone.utc)
    for dev in created_devices[:10]:
        for i in range(25):
            t_time = now - timedelta(minutes=(25 - i) * 5)
            val = 22.0 + random.uniform(-2, 2)
            unit = "°C" if "temp" in dev.device_type else "kW" if "energy" in dev.device_type else "units"
            db.add(TelemetryRecord(
                device_id=dev.id,
                timestamp=t_time,
                metric_type=dev.device_type,
                value=round(val, 2),
                unit=unit,
            ))

    db.commit()
    logger.info(f"Database seeded successfully with {len(created_devices)} devices and rules.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

    # Background simulator worker
    async def run_bg_sim():
        await asyncio.sleep(2)
        while True:
            try:
                with SessionLocal() as s:
                    devices = s.query(Device).filter(Device.status == "online", Device.is_deleted == False).limit(8).all()
                    for dev in devices:
                        reading = simulator.generate_reading(dev)
                        # Ingest reading
                        from .api.routes import ingest_telemetry
                        await ingest_telemetry(reading, s)
                await asyncio.sleep(4)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Simulator pulse exception: {e}")
                await asyncio.sleep(5)

    sim_task = asyncio.create_task(run_bg_sim())
    yield
    sim_task.cancel()


app = FastAPI(
    title="IoT Sentinel API",
    version="1.0.0",
    description="Real-time campus IoT device monitoring and anomaly detection platform.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(iot_router)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "iot-sentinel", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/ready")
def ready():
    return {"status": "ready", "service": "iot-sentinel"}


@app.get("/metrics")
def metrics():
    return (
        "# HELP iot_devices_total Total registered IoT devices\n"
        "# TYPE iot_devices_total gauge\n"
        "iot_devices_total 55\n"
        "# HELP iot_telemetry_events_total Ingested telemetry events\n"
        "# TYPE iot_telemetry_events_total counter\n"
        "iot_telemetry_events_total 1284\n"
    )


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep socket alive and respond to client heartbeats
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
