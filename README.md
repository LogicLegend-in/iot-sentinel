# IoT Sentinel — Smart Campus IoT Monitoring & Anomaly Detection

[![LogicLegend](https://img.shields.io/badge/LogicLegend-Ecosystem-6366f1.svg)](https://github.com/LogicLegend-in)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![WebSockets](https://img.shields.io/badge/WebSockets-Realtime-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-Passing%20(6%2F6)-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**IoT Sentinel** is a distributed IoT telemetry ingestion, real-time stream processing, and multi-strategy anomaly detection platform designed for smart campus infrastructure.

Part of the [**LogicLegend.in**](https://github.com/LogicLegend-in) open-source technology ecosystem.

---

## Key Features

- **High-Throughput Telemetry Ingestion**: REST and streaming endpoints collecting sensor readings (temperature, humidity, HVAC, energy draw, air quality index, occupancy, water pressure).
- **Multi-Strategy Anomaly Detection Engine**:
  - **Rule-Based Thresholds**: Instant alarms on critical boundary violations (e.g., severe overheating, low battery).
  - **Statistical Z-Score Engine**: Identifies sudden distribution shifts beyond 3 standard deviations.
  - **Isolation Forest ML**: Scikit-Learn tree ensemble for multivariate anomaly clustering with natural language diagnostics.
- **Autonomous Device Simulator**: Built-in background worker simulating 5 multi-sensor campus buildings for testing and demonstration.
- **Real-Time WebSockets**: Live broadcast to connected operations dashboards via `/ws/telemetry`.
- **Prometheus Metrics**: Built-in `/metrics` endpoint for infrastructure observability.
- **Interactive Operations Command Center**: Real-time telemetry timelines, active incident triage workflows, and interactive campus map view.

---

## Architecture

```
iot-sentinel/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routes (devices, telemetry, incidents)
│   │   ├── core/         # Simulator and anomaly detection parameters
│   │   ├── models/       # Schemas for devices, telemetry & incidents
│   │   ├── services/     # Ingestion, Isolation Forest ML & WebSocket manager
│   │   └── main.py       # FastAPI application entrypoint
│   ├── tests/            # Automated test suite (6 tests passing)
│   ├── Dockerfile        # Container specification
│   └── requirements.txt  # Python dependencies
├── frontend/
│   └── index.html        # Real-time IoT monitoring command center
├── shared/               # Shared database, logging, auth & security handlers
├── docker-compose.yml    # Docker Compose deployment
└── README.md
```

---

## Quick Start

### 1. Local Setup

```bash
# Clone repository
git clone https://github.com/LogicLegend-in/iot-sentinel.git
cd iot-sentinel

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Run backend (default: http://localhost:8001)
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8001 --reload
```

Open `frontend/index.html` in your browser to view the real-time IoT dashboard.

### 2. Docker Setup

```bash
# Build and run with Docker Compose
docker compose up --build
```

Access Prometheus metrics at `http://localhost:8001/metrics` and Swagger API docs at `http://localhost:8001/docs`.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Healthcheck probe |
| `GET` | `/metrics` | Prometheus telemetry & anomaly counters |
| `POST` | `/api/v1/iot/telemetry/ingest` | Batch ingest sensor readings |
| `GET` | `/api/v1/iot/devices` | Query registered campus IoT sensors |
| `GET` | `/api/v1/iot/incidents` | Active and historical incident logs |
| `POST` | `/api/v1/iot/incidents/{id}/acknowledge` | Acknowledge and triage an incident |
| `WS` | `/ws/telemetry` | Real-time sensor stream WebSocket |

---

## Running Tests

```bash
python -m pytest backend/tests -v
```

---

## License

Distributed under the MIT License. Built with ❤️ by [LogicLegend](https://github.com/LogicLegend-in).
