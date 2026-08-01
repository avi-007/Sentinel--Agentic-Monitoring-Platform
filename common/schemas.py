"""Message contracts exchanged over Kafka, and the shared metric-snapshot shape
used in both Kafka payloads and Postgres JSONB columns. Kept as pydantic models
so producers get validation/serialization for free and consumers get a typed
`.model_validate_json()` parse instead of hand-rolled dict access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MetricSnapshot(BaseModel):
    cpu_pct: float
    mem_pct: float
    latency_ms: float
    error_rate_pct: float


class InjectedAnomaly(BaseModel):
    """Ground-truth debug info from the generator. The detector never reads
    this field — it exists purely so a human (or an eval script) can compare
    detected anomalies against what was actually injected.
    """

    active: bool = False
    type: Optional[Literal["spike", "ramp"]] = None


class TelemetryEvent(BaseModel):
    """Published by the generator to `telemetry.raw`, keyed by host_id."""

    event_id: UUID = Field(default_factory=uuid4)
    host_id: str
    service_name: str
    timestamp: datetime = Field(default_factory=utcnow)
    metrics: MetricSnapshot
    injected_anomaly: InjectedAnomaly = Field(default_factory=InjectedAnomaly)


class AlertEvent(BaseModel):
    """Published by the detector to `alerts.triggered`, keyed by host_id, once
    a score crosses the dynamic threshold and the per-host cooldown allows it.
    """

    alert_id: UUID = Field(default_factory=uuid4)
    host_id: str
    service_name: str
    triggered_at: datetime = Field(default_factory=utcnow)
    raw_score: float
    threshold: float
    ewma_mean: float
    ewma_std: float
    severity: Literal["warning", "critical"]
    metric_snapshot: MetricSnapshot
    recent_metrics: list[MetricSnapshot] = Field(default_factory=list)
    is_early_warning: bool = False
    predicted_breach_minutes: Optional[float] = None
