"""Detector service entrypoint: consumes `telemetry.raw`, scores each event
with a per-host IsolationForest, applies the dynamic threshold, writes every
scored event to Postgres, and publishes to `alerts.triggered` when warranted.
"""

from __future__ import annotations

import structlog

from common import db
from common.kafka_utils import make_consumer, make_producer, consume_json_forever, wait_for_broker
from common.logging_conf import configure_logging
from common.schemas import AlertEvent, MetricSnapshot, TelemetryEvent

from . import db_writer, dynamic_threshold, model_store, trend_forecast
from .config import DetectorSettings
from .feature_engineering import compute_feature_vector
from .host_state import HostStateRegistry

log = structlog.get_logger(__name__)


def make_handler(settings: DetectorSettings, registry: HostStateRegistry, producer):
    def handle(_key: str, payload: dict) -> None:
        event = TelemetryEvent.model_validate(payload)
        state = registry.get(event.host_id)
        metrics_dict = event.metrics.model_dump()

        # compute_feature_vector also updates state.raw_buffer / state.last_raw
        # as a side effect, so it must run exactly once per event.
        feature_vector = compute_feature_vector(state, metrics_dict)
        raw_score = model_store.ingest_and_score(state, feature_vector, settings)

        injected_type = event.injected_anomaly.type if event.injected_anomaly.active else None

        if raw_score is None:
            # Still warming up: no model yet, nothing to score or alert on.
            db_writer.insert_metric_row(
                event_id=event.event_id,
                host_id=event.host_id,
                service_name=event.service_name,
                ts=event.timestamp,
                metrics=metrics_dict,
                features=feature_vector.tolist(),
                raw_score=None,
                ewma_mean=None,
                ewma_std=None,
                threshold=None,
                is_anomaly=False,
                severity=None,
                model_version=None,
                injected_anomaly_type=injected_type,
                predicted_breach_minutes=None,
            )
            return

        result = dynamic_threshold.evaluate(state, raw_score, settings, now=event.timestamp)
        predicted_breach_minutes = trend_forecast.evaluate(
            state, raw_score, result.threshold, result.is_anomaly, event.timestamp, settings
        )

        metrics_id = db_writer.insert_metric_row(
            event_id=event.event_id,
            host_id=event.host_id,
            service_name=event.service_name,
            ts=event.timestamp,
            metrics=metrics_dict,
            features=feature_vector.tolist(),
            raw_score=raw_score,
            ewma_mean=result.ewma_mean,
            ewma_std=result.ewma_std,
            threshold=result.threshold,
            is_anomaly=result.is_anomaly,
            severity=result.severity,
            model_version=state.model_version,
            injected_anomaly_type=injected_type,
            predicted_breach_minutes=predicted_breach_minutes,
        )

        if result.should_publish_alert:
            alert = AlertEvent(
                host_id=event.host_id,
                service_name=event.service_name,
                triggered_at=event.timestamp,
                raw_score=raw_score,
                threshold=result.threshold,
                ewma_mean=result.ewma_mean,
                ewma_std=result.ewma_std,
                severity=result.severity,
                metric_snapshot=event.metrics,
                recent_metrics=[MetricSnapshot(**m) for m in state.recent_metric_snapshots()],
            )
            db_writer.insert_alert_row(alert, metrics_id)
            db_writer.publish_alert(producer, settings.topic_alerts_triggered, alert)

        if predicted_breach_minutes is not None:
            cooldown_active = (
                state.last_early_warning_time is not None
                and (event.timestamp - state.last_early_warning_time).total_seconds()
                < settings.det_alert_cooldown_seconds
            )
            if not cooldown_active:
                early_warning = AlertEvent(
                    host_id=event.host_id,
                    service_name=event.service_name,
                    triggered_at=event.timestamp,
                    raw_score=raw_score,
                    threshold=result.threshold,
                    ewma_mean=result.ewma_mean,
                    ewma_std=result.ewma_std,
                    severity="warning",
                    metric_snapshot=event.metrics,
                    recent_metrics=[MetricSnapshot(**m) for m in state.recent_metric_snapshots()],
                    is_early_warning=True,
                    predicted_breach_minutes=predicted_breach_minutes,
                )
                state.last_early_warning_time = event.timestamp
                db_writer.insert_alert_row(early_warning, metrics_id)
                db_writer.publish_alert(producer, settings.topic_alerts_triggered, early_warning)

    return handle


def main() -> None:
    settings = DetectorSettings()
    configure_logging("detector", settings.log_level)

    db.init_pool(settings.dsn)
    wait_for_broker(settings.kafka_bootstrap_servers)

    producer = make_producer(settings.kafka_bootstrap_servers)
    consumer = make_consumer(
        settings.kafka_bootstrap_servers,
        group_id=settings.detector_consumer_group,
        topics=[settings.topic_telemetry_raw],
    )

    registry = HostStateRegistry(
        rolling_window=settings.det_rolling_window,
        train_window_size=settings.det_train_window_size,
        score_history_size=settings.det_score_history_size,
        trend_window_size=settings.det_trend_window_size,
    )

    log.info("detector.started", warmup_events=settings.det_warmup_events)
    consume_json_forever(consumer, make_handler(settings, registry, producer))


if __name__ == "__main__":
    main()
