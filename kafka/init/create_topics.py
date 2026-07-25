"""One-shot job: wait for the broker, then idempotently create Sentinel's
topics with explicit partition counts. Runs as the `kafka-init` compose
service; other services depend on it via `condition: service_completed_successfully`
rather than relying on broker auto-create.
"""

import os
import sys

sys.path.insert(0, "/app")  # see Dockerfile: repo root COPYed to /app

from common.kafka_utils import create_topics_idempotent, wait_for_broker
from common.logging_conf import configure_logging
from common.topics import ALL_TOPICS
import structlog

configure_logging("kafka-init", os.environ.get("LOG_LEVEL", "INFO"))
log = structlog.get_logger(__name__)


def main() -> None:
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    log.info("kafka_init.waiting_for_broker", bootstrap=bootstrap)
    wait_for_broker(bootstrap, timeout_seconds=90)
    log.info("kafka_init.creating_topics", topics=[t[0] for t in ALL_TOPICS])
    create_topics_idempotent(bootstrap, ALL_TOPICS)
    log.info("kafka_init.done")


if __name__ == "__main__":
    main()
