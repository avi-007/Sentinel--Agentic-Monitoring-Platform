"""Kafka topic name + partition constants, shared by every service and by
kafka/init/create_topics.py. Names/partition counts are also overridable via
env vars so a single source of truth (this file's defaults) stays in sync with
.env.example without needing to edit two places for a quick experiment.
"""

import os


TOPIC_TELEMETRY_RAW = os.environ.get("TOPIC_TELEMETRY_RAW", "telemetry.raw")
TOPIC_ALERTS_TRIGGERED = os.environ.get("TOPIC_ALERTS_TRIGGERED", "alerts.triggered")

TOPIC_TELEMETRY_PARTITIONS = int(os.environ.get("TOPIC_TELEMETRY_PARTITIONS", "4"))
TOPIC_ALERTS_PARTITIONS = int(os.environ.get("TOPIC_ALERTS_PARTITIONS", "2"))

# (topic_name, partitions, replication_factor) — single broker demo, RF=1.
ALL_TOPICS = [
    (TOPIC_TELEMETRY_RAW, TOPIC_TELEMETRY_PARTITIONS, 1),
    (TOPIC_ALERTS_TRIGGERED, TOPIC_ALERTS_PARTITIONS, 1),
]
