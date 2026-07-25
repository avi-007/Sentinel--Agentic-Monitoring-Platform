"""Agent service entrypoint: consumes `alerts.triggered`, runs a multi-turn
tool-calling investigation (mock or real GPT-4o per LLM_PROVIDER), and
persists the reasoning transcript + diagnosis to Postgres.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import partial

import structlog

from common import db
from common.kafka_utils import make_consumer, consume_json_forever, wait_for_broker
from common.logging_conf import configure_logging
from common.schemas import AlertEvent

from . import db_writer
from .alert_context import build_alert_context
from .config import AgentSettings
from .llm_client import build_llm_client
from .tool_loop import run_investigation
from .tools import TOOL_FUNCTIONS

log = structlog.get_logger(__name__)


def make_handler(settings: AgentSettings, llm_client):
    model_name = settings.openai_model if settings.llm_provider == "openai" else "mock"

    def handle(_key: str, payload: dict) -> None:
        alert = AlertEvent.model_validate(payload)
        log.info("agent.alert_received", alert_id=str(alert.alert_id), host_id=alert.host_id)
        db_writer.update_alert_status(str(alert.alert_id), "investigating")

        ctx = build_alert_context(alert)
        tool_functions = {name: partial(fn, ctx=ctx) for name, fn in TOOL_FUNCTIONS.items()}

        started_at = datetime.now(timezone.utc)
        result = None
        status = "completed"
        error_message = None
        try:
            result = run_investigation(ctx, llm_client, tool_functions, settings.agent_max_tool_turns)
        except Exception as exc:  # noqa: BLE001 - one failed investigation shouldn't kill the consumer
            log.exception("agent.investigation_failed", alert_id=str(alert.alert_id))
            status = "failed"
            error_message = str(exc)
        completed_at = datetime.now(timezone.utc)

        db_writer.persist_agent_run(
            alert_id=str(alert.alert_id),
            llm_provider=settings.llm_provider,
            model_name=model_name,
            started_at=started_at,
            completed_at=completed_at,
            result=result,
            status=status,
            error_message=error_message,
        )
        db_writer.update_alert_status(str(alert.alert_id), "diagnosed" if status == "completed" else "error")

        log.info(
            "agent.investigation_complete",
            alert_id=str(alert.alert_id),
            status=status,
            confidence=result.confidence if result else None,
            turn_count=result.turn_count if result else None,
        )

    return handle


def main() -> None:
    settings = AgentSettings()
    configure_logging("agent", settings.log_level)

    db.init_pool(settings.dsn)
    wait_for_broker(settings.kafka_bootstrap_servers)

    consumer = make_consumer(
        settings.kafka_bootstrap_servers,
        group_id=settings.agent_consumer_group,
        topics=[settings.topic_alerts_triggered],
    )
    llm_client = build_llm_client(
        settings.llm_provider,
        settings.openai_api_key,
        settings.openai_model,
        settings.agent_request_timeout_seconds,
        settings.agent_mock_seed,
    )

    log.info("agent.started", provider=settings.llm_provider)
    consume_json_forever(consumer, make_handler(settings, llm_client))


if __name__ == "__main__":
    main()
