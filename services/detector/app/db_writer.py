"""Persistence + alert publishing for the detector. The detector is the source
of truth for "an alert happened": it inserts the `alerts` row itself (status
`new`) before publishing to Kafka, so there's no create/race ambiguity with the
agent service, which only ever UPDATEs that row's status.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import orjson
import structlog
from confluent_kafka import Producer

from common import db
from common.kafka_utils import produce_json
from common.schemas import AlertEvent

log = structlog.get_logger(__name__)


def insert_metric_row(
    event_id: UUID,
    host_id: str,
    service_name: str,
    ts,
    metrics: dict,
    features: list[float],
    raw_score: Optional[float],
    ewma_mean: Optional[float],
    ewma_std: Optional[float],
    threshold: Optional[float],
    is_anomaly: bool,
    severity: Optional[str],
    model_version: Optional[int],
    injected_anomaly_type: Optional[str],
) -> int:
    row = db.fetch_one(
        """
        INSERT INTO metrics (
            event_id, host_id, service_name, ts,
            cpu_pct, mem_pct, latency_ms, error_rate_pct,
            features, raw_score, ewma_mean, ewma_std, threshold,
            is_anomaly, severity, model_version, injected_anomaly_type
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            str(event_id),
            host_id,
            service_name,
            ts,
            metrics["cpu_pct"],
            metrics["mem_pct"],
            metrics["latency_ms"],
            metrics["error_rate_pct"],
            orjson.dumps(list(features)).decode("utf-8"),
            raw_score,
            ewma_mean,
            ewma_std,
            threshold,
            is_anomaly,
            severity,
            model_version,
            injected_anomaly_type,
        ),
    )
    return row["id"]


def insert_alert_row(alert: AlertEvent, metrics_id: int) -> None:
    db.execute(
        """
        INSERT INTO alerts (
            alert_id, host_id, service_name, triggered_at,
            raw_score, threshold, severity, metric_snapshot, metrics_id, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'new')
        """,
        (
            str(alert.alert_id),
            alert.host_id,
            alert.service_name,
            alert.triggered_at,
            alert.raw_score,
            alert.threshold,
            alert.severity,
            orjson.dumps(alert.metric_snapshot.model_dump()).decode("utf-8"),
            metrics_id,
        ),
    )


def publish_alert(producer: Producer, topic: str, alert: AlertEvent) -> None:
    produce_json(producer, topic, key=alert.host_id, payload=alert.model_dump(mode="json"))
    log.info(
        "detector.alert_published",
        alert_id=str(alert.alert_id),
        host_id=alert.host_id,
        severity=alert.severity,
        raw_score=alert.raw_score,
        threshold=alert.threshold,
    )
