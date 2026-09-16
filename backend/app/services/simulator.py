"""
IoT Device Simulator Service.
Generates realistic multi-campus sensor telemetry streams (temperature, energy, humidity, air quality, occupancy, water level)
and injects realistic operational variations and anomalies.
"""

import asyncio
from datetime import datetime, timezone
import math
import random
from typing import Callable, Dict, List, Optional
from ..models.schemas import Device, DeviceType, TelemetryIngest


class DeviceSimulator:
    """Emulates a smart campus network of physical IoT devices transmitting over HTTP / MQTT."""

    def __init__(self):
        self.is_running = False
        self._step_counter = 0

    def generate_reading(self, device: Device) -> TelemetryIngest:
        self._step_counter += 1
        now = datetime.now(timezone.utc)
        # Diurnal sinusoidal base pattern
        time_factor = math.sin(self._step_counter * 0.1)

        metric_type = device.device_type
        value = 20.0
        unit = "units"

        # Occasional anomaly injection (roughly 3% probability)
        should_inject_anomaly = (random.random() < 0.04)

        if metric_type == DeviceType.TEMPERATURE.value:
            unit = "°C"
            base_temp = 22.0 + (time_factor * 2.5) + random.uniform(-0.5, 0.5)
            value = (base_temp + 20.0) if should_inject_anomaly else base_temp

        elif metric_type == DeviceType.HUMIDITY.value:
            unit = "%"
            base_hum = 45.0 + (time_factor * 5.0) + random.uniform(-1.0, 1.0)
            value = 92.0 if should_inject_anomaly else base_hum

        elif metric_type == DeviceType.ENERGY_METER.value:
            unit = "kW"
            base_kw = 12.5 + (abs(time_factor) * 15.0) + random.uniform(-0.8, 0.8)
            value = (base_kw * 3.5) if should_inject_anomaly else base_kw

        elif metric_type == DeviceType.AIR_QUALITY.value:
            unit = "AQI"
            base_aqi = 35.0 + random.uniform(-3.0, 3.0)
            value = 210.0 if should_inject_anomaly else base_aqi

        elif metric_type == DeviceType.OCCUPANCY.value:
            unit = "persons"
            base_occ = max(0.0, float(int(25.0 + (time_factor * 20.0) + random.uniform(-2, 2))))
            value = 180.0 if should_inject_anomaly else base_occ

        elif metric_type == DeviceType.WATER_LEVEL.value:
            unit = "meters"
            base_water = 3.5 + random.uniform(-0.1, 0.1)
            value = 5.8 if should_inject_anomaly else base_water

        elif metric_type == DeviceType.HVAC.value:
            unit = "airflow_cfm"
            base_cfm = 450.0 + (time_factor * 50.0) + random.uniform(-10, 10)
            value = 50.0 if should_inject_anomaly else base_cfm

        else:
            value = 50.0 + random.uniform(-5, 5)

        # Battery slightly drains over time or stays healthy
        current_battery = max(5.0, (device.battery_level or 95.0) - random.uniform(0.001, 0.005))
        if should_inject_anomaly and random.random() < 0.2:
            current_battery = 12.0  # Trigger battery rule alert

        return TelemetryIngest(
            device_id=device.id,
            metric_type=metric_type,
            value=round(value, 2),
            unit=unit,
            timestamp=now,
            battery_level=round(current_battery, 1),
            signal_strength_rssi=int(device.signal_strength_rssi + random.randint(-2, 2)),
        )

    async def run_simulation_loop(
        self,
        get_devices_fn: Callable[[], List[Device]],
        process_telemetry_fn: Callable[[TelemetryIngest], Any],
        interval_seconds: float = 3.0,
    ):
        """Asynchronous background loop pushing simulated telemetry pulses."""
        self.is_running = True
        while self.is_running:
            try:
                devices = get_devices_fn()
                for dev in devices:
                    if dev.status == "online":
                        reading = self.generate_reading(dev)
                        await process_telemetry_fn(reading)
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(interval_seconds)

    def stop(self):
        self.is_running = False


simulator = DeviceSimulator()
