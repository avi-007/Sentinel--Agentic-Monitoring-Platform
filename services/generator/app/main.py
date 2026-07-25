"""Generator service entrypoint: ticks every GEN_TICK_INTERVAL_SECONDS, produces
one TelemetryEvent per host to `telemetry.raw`, forever.
"""

from __future__ import annotations

import time

import structlog

from common import db
from common.kafka_utils import make_producer, produce_json, wait_for_broker
from common.logging_conf import configure_logging
from common.schemas import InjectedAnomaly, MetricSnapshot, TelemetryEvent

from .anomaly_injector import AnomalyInjector
from .config import GeneratorSettings
from .host_profiles import HOST_PROFILES
from .signal_model import HostSignalGenerator

log = structlog.get_logger(__name__)


def seed_hosts(settings: GeneratorSettings) -> None:
    db.init_pool(settings.dsn)
    for profile in HOST_PROFILES:
        db.execute(
            """
            INSERT INTO hosts (host_id, service_name)
            VALUES (%s, %s)
            ON CONFLICT (host_id) DO NOTHING
            """,
            (profile.host_id, profile.service_name),
        )
    log.info("generator.hosts_seeded", count=len(HOST_PROFILES))


def run(settings: GeneratorSettings) -> None:
    wait_for_broker(settings.kafka_bootstrap_servers)
    producer = make_producer(settings.kafka_bootstrap_servers)

    generators = {
        p.host_id: HostSignalGenerator(p, settings.gen_time_scale_factor) for p in HOST_PROFILES
    }
    injectors = {
        p.host_id: AnomalyInjector(
            settings.gen_anomaly_injection_rate, settings.gen_anomaly_cooldown_ticks, seed=p.seed + 1000
        )
        for p in HOST_PROFILES
    }

    log.info(
        "generator.started",
        hosts=len(HOST_PROFILES),
        tick_interval=settings.gen_tick_interval_seconds,
        time_scale_factor=settings.gen_time_scale_factor,
    )

    tick_count = 0
    while True:
        tick_start = time.monotonic()
        for profile in HOST_PROFILES:
            base_metrics = generators[profile.host_id].tick(settings.gen_tick_interval_seconds)
            final_metrics, anomaly_info = injectors[profile.host_id].maybe_inject(base_metrics)

            event = TelemetryEvent(
                host_id=profile.host_id,
                service_name=profile.service_name,
                metrics=MetricSnapshot(**final_metrics),
                injected_anomaly=InjectedAnomaly(**anomaly_info),
            )
            produce_json(
                producer,
                settings.topic_telemetry_raw,
                key=profile.host_id,
                payload=event.model_dump(mode="json"),
            )

        producer.poll(0)
        tick_count += 1
        if tick_count % 20 == 0:
            producer.flush(5)
            log.info("generator.tick", tick=tick_count)

        elapsed = time.monotonic() - tick_start
        time.sleep(max(0.0, settings.gen_tick_interval_seconds - elapsed))


def main() -> None:
    settings = GeneratorSettings()
    configure_logging("generator", settings.log_level)
    seed_hosts(settings)
    run(settings)


if __name__ == "__main__":
    main()
