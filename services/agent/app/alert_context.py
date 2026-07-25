"""Small per-alert context object bound into the mocked tools (see tools/) so
each tool call is grounded in the specific alert being investigated, without
exposing host_id/service_name as LLM-controlled tool parameters (the model
already knows those from the system/user prompt — no reason to let it, or make
it, respecify them per call).
"""

from __future__ import annotations

from dataclasses import dataclass

from common.schemas import AlertEvent

METRIC_NAMES = ["cpu_pct", "mem_pct", "latency_ms", "error_rate_pct"]


@dataclass(frozen=True)
class AlertContext:
    alert_id: str
    host_id: str
    service_name: str
    severity: str
    raw_score: float
    threshold: float
    triggered_at: str
    metric_snapshot: dict
    dominant_metric: str


def _compute_dominant_metric(alert: AlertEvent) -> str:
    """Picks whichever metric deviates most (in z-score terms) from its recent
    rolling history — this is what the synthetic log/deploy generators bias
    toward, so the tool outputs tell a coherent, solvable story.
    """
    if not alert.recent_metrics:
        return "latency_ms"

    best_metric = "latency_ms"
    best_z = -1.0
    for metric in METRIC_NAMES:
        values = [getattr(m, metric) for m in alert.recent_metrics]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = variance**0.5
        current = getattr(alert.metric_snapshot, metric)
        z = abs((current - mean) / std) if std > 1e-6 else 0.0
        if z > best_z:
            best_z = z
            best_metric = metric
    return best_metric


def build_alert_context(alert: AlertEvent) -> AlertContext:
    return AlertContext(
        alert_id=str(alert.alert_id),
        host_id=alert.host_id,
        service_name=alert.service_name,
        severity=alert.severity,
        raw_score=alert.raw_score,
        threshold=alert.threshold,
        triggered_at=alert.triggered_at.isoformat(),
        metric_snapshot=alert.metric_snapshot.model_dump(),
        dominant_metric=_compute_dominant_metric(alert),
    )
