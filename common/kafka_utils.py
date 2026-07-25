"""Thin wrappers around confluent-kafka's Producer/Consumer/AdminClient so
services don't each re-implement JSON encoding, delivery-report logging, and
topic-existence checks.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, Optional

import orjson
import structlog
from confluent_kafka import Consumer, KafkaException, Message, Producer
from confluent_kafka.admin import AdminClient, NewTopic

log = structlog.get_logger(__name__)


def make_producer(bootstrap_servers: str) -> Producer:
    return Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            # small linger to batch a bit without materially delaying a demo
            "linger.ms": 50,
            "acks": "all",
        }
    )


def _delivery_report(err, msg: Message) -> None:
    if err is not None:
        log.error("kafka.delivery_failed", error=str(err), topic=msg.topic())


def produce_json(producer: Producer, topic: str, key: str, payload: dict) -> None:
    producer.produce(
        topic,
        key=key.encode("utf-8"),
        value=orjson.dumps(payload),
        callback=_delivery_report,
    )
    producer.poll(0)


def make_consumer(
    bootstrap_servers: str, group_id: str, topics: Iterable[str]
) -> Consumer:
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    consumer.subscribe(list(topics))
    return consumer


def consume_json_forever(
    consumer: Consumer,
    handler: Callable[[str, dict], None],
    poll_timeout: float = 1.0,
) -> None:
    """Blocking loop: poll, decode JSON, call handler(key, value_dict). Swallows
    and logs per-message handler errors so one bad/unexpected message doesn't
    kill the whole consumer loop.
    """
    try:
        while True:
            msg = consumer.poll(poll_timeout)
            if msg is None:
                continue
            if msg.error():
                log.error("kafka.consume_error", error=str(msg.error()))
                continue
            try:
                key = msg.key().decode("utf-8") if msg.key() else ""
                value = orjson.loads(msg.value())
                handler(key, value)
            except Exception:
                log.exception("kafka.handler_failed", topic=msg.topic())
    finally:
        consumer.close()


def wait_for_broker(bootstrap_servers: str, timeout_seconds: int = 60) -> None:
    """Polls the broker's metadata until it responds or timeout_seconds elapse.
    Used by kafka-init before creating topics, and as a defensive startup check
    in each service (compose healthchecks/depends_on cover most of this, but a
    small retry loop is cheap insurance against a slow-starting broker).
    """
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    deadline = time.time() + timeout_seconds
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            admin.list_topics(timeout=5)
            return
        except KafkaException as exc:  # broker not ready yet
            last_err = exc
            time.sleep(2)
    raise RuntimeError(f"Kafka broker not reachable after {timeout_seconds}s: {last_err}")


def create_topics_idempotent(
    bootstrap_servers: str, topics: Iterable[tuple[str, int, int]]
) -> None:
    """topics: iterable of (name, num_partitions, replication_factor). Safe to
    call repeatedly — already-existing topics are skipped, not errored on.
    """
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    existing = set(admin.list_topics(timeout=10).topics.keys())
    to_create = [
        NewTopic(name, num_partitions=parts, replication_factor=rf)
        for name, parts, rf in topics
        if name not in existing
    ]
    if not to_create:
        log.info("kafka.topics_already_exist", topics=[t[0] for t in topics])
        return
    futures = admin.create_topics(to_create)
    for name, future in futures.items():
        try:
            future.result()
            log.info("kafka.topic_created", topic=name)
        except KafkaException as exc:
            log.error("kafka.topic_create_failed", topic=name, error=str(exc))
            raise
