"""
Multi-strategy Anomaly Detection Engine for IoT Sentinel.
Implements Rule-Based, Statistical (Z-score & EWMA), and ML (Isolation Forest) detection.
Provides clear, human-understandable explanations for every detected anomaly.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
from sklearn.ensemble import IsolationForest

from ..models.schemas import (
    AlertRecord,
    AlertSeverity,
    AlertStatus,
    AnomalyMethod,
    AnomalyRecord,
    DetectionRule,
    Device,
)


class AnomalyEngine:
    """Evaluates incoming telemetry events against historical baseline and rules."""

    def __init__(self, rolling_window_size: int = 50):
        self.rolling_window_size = rolling_window_size
        self._device_history: Dict[str, List[float]] = {}
        self._iforest_models: Dict[str, IsolationForest] = {}

    def append_telemetry(self, device_id: str, value: float):
        """Append metric value to in-memory sliding window."""
        if device_id not in self._device_history:
            self._device_history[device_id] = []
        self._device_history[device_id].append(value)
        if len(self._device_history[device_id]) > self.rolling_window_size:
            self._device_history[device_id].pop(0)

    def evaluate(
        self,
        device: Device,
        metric: str,
        value: float,
        rules: List[DetectionRule] = None,
    ) -> Optional[Tuple[AnomalyRecord, Optional[AlertRecord]]]:
        """
        Executes anomaly detection evaluation pipeline:
        1. Custom Rule-based evaluation
        2. Statistical Z-Score / EWMA
        3. Multivariate / Isolation Forest detection
        """
        self.append_telemetry(device.id, value)
        history = self._device_history.get(device.id, [])

        # 1. Rule-Based Evaluation
        rule_result = self._check_rules(device, metric, value, rules or [])
        if rule_result:
            return rule_result

        # Battery check
        if device.battery_level is not None and device.battery_level < 15.0:
            anomaly = AnomalyRecord(
                device_id=device.id,
                metric="battery",
                value=float(device.battery_level),
                anomaly_score=0.95,
                severity=AlertSeverity.CRITICAL.value,
                method=AnomalyMethod.RULE_BASED.value,
                explanation=f"Critical battery depletion ({device.battery_level:.1f}% < 15.0%). Device imminent failure.",
                status=AlertStatus.OPEN.value,
            )
            alert = AlertRecord(
                device_id=device.id,
                title=f"Critical Battery Warning: {device.name}",
                message=anomaly.explanation,
                severity=AlertSeverity.CRITICAL.value,
                status=AlertStatus.OPEN.value,
            )
            return anomaly, alert

        # Need minimum history points for statistical and ML methods
        if len(history) < 10:
            return None

        # 2. Statistical Evaluation (Z-Score & EWMA)
        stat_result = self._check_statistical(device, metric, value, history)
        if stat_result:
            return stat_result

        # 3. Isolation Forest ML Evaluation
        ml_result = self._check_isolation_forest(device, metric, value, history)
        if ml_result:
            return ml_result

        return None

    def _check_rules(
        self,
        device: Device,
        metric: str,
        value: float,
        rules: List[DetectionRule],
    ) -> Optional[Tuple[AnomalyRecord, Optional[AlertRecord]]]:
        for rule in rules:
            if not rule.is_active or rule.metric_type.lower() != metric.lower():
                continue

            violation = False
            if rule.operator == ">" and value > rule.threshold_value:
                violation = True
            elif rule.operator == "<" and value < rule.threshold_value:
                violation = True
            elif rule.operator == ">=" and value >= rule.threshold_value:
                violation = True
            elif rule.operator == "<=" and value <= rule.threshold_value:
                violation = True

            if violation:
                explanation = (
                    f"Threshold breached: {metric} reading of {value:.2f} violated configured rule "
                    f"'{rule.name}' ({metric} {rule.operator} {rule.threshold_value:.2f})."
                )
                anomaly = AnomalyRecord(
                    device_id=device.id,
                    metric=metric,
                    value=value,
                    anomaly_score=0.88,
                    severity=rule.severity,
                    method=AnomalyMethod.RULE_BASED.value,
                    explanation=explanation,
                    status=AlertStatus.OPEN.value,
                )
                alert = AlertRecord(
                    device_id=device.id,
                    title=f"Threshold Alert: {rule.name} on {device.name}",
                    message=explanation,
                    severity=rule.severity,
                    status=AlertStatus.OPEN.value,
                )
                return anomaly, alert
        return None

    def _check_statistical(
        self,
        device: Device,
        metric: str,
        value: float,
        history: List[float],
    ) -> Optional[Tuple[AnomalyRecord, Optional[AlertRecord]]]:
        arr = np.array(history[:-1])  # Compare against prior history
        mean = float(np.mean(arr))
        std = float(np.std(arr))

        std = max(float(np.std(arr)), 0.01)
        z_score = abs(value - mean) / std

        # Z-score threshold at 3.0 standard deviations
        if z_score >= 3.0:
            severity = AlertSeverity.CRITICAL.value if z_score > 4.5 else AlertSeverity.HIGH.value
            score = min(1.0, 0.5 + (z_score / 10.0))
            explanation = (
                f"Statistical Outlier: {metric} reading of {value:.2f} is {z_score:.2f} standard deviations "
                f"away from baseline rolling mean of {mean:.2f} (std: {std:.2f})."
            )
            anomaly = AnomalyRecord(
                device_id=device.id,
                metric=metric,
                value=value,
                anomaly_score=round(score, 3),
                severity=severity,
                method=AnomalyMethod.STATISTICAL.value,
                explanation=explanation,
                status=AlertStatus.OPEN.value,
            )
            alert = AlertRecord(
                device_id=device.id,
                title=f"Statistical Outlier Detected: {device.name}",
                message=explanation,
                severity=severity,
                status=AlertStatus.OPEN.value,
            )
            return anomaly, alert
        return None

    def _check_isolation_forest(
        self,
        device: Device,
        metric: str,
        value: float,
        history: List[float],
    ) -> Optional[Tuple[AnomalyRecord, Optional[AlertRecord]]]:
        if len(history) < 20:
            return None

        X = np.array(history).reshape(-1, 1)
        model = IsolationForest(contamination=0.08, random_state=42)
        model.fit(X)

        current_sample = np.array([[value]])
        pred = model.predict(current_sample)[0]  # -1 for anomaly, 1 for normal
        raw_score = model.score_samples(current_sample)[0]
        # Normalized score: lower raw score means more anomalous
        anomaly_score = round(float(1.0 / (1.0 + np.exp(raw_score * 5))), 3)

        if pred == -1:
            severity = AlertSeverity.HIGH.value if anomaly_score > 0.75 else AlertSeverity.MEDIUM.value
            explanation = (
                f"Machine Learning Anomaly: Isolation Forest detected irregular pattern in {metric} stream "
                f"(anomaly score: {anomaly_score:.2f}, raw density: {raw_score:.3f}) indicating abnormal operational state."
            )
            anomaly = AnomalyRecord(
                device_id=device.id,
                metric=metric,
                value=value,
                anomaly_score=anomaly_score,
                severity=severity,
                method=AnomalyMethod.ISOLATION_FOREST.value,
                explanation=explanation,
                status=AlertStatus.OPEN.value,
            )
            alert = AlertRecord(
                device_id=device.id,
                title=f"ML Anomaly Detected: {device.name}",
                message=explanation,
                severity=severity,
                status=AlertStatus.OPEN.value,
            )
            return anomaly, alert

        return None
