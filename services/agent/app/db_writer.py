from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import orjson

from common import db

from .tool_loop import InvestigationResult


def update_alert_status(alert_id: str, status: str) -> None:
    db.execute(
        "UPDATE alerts SET status = %s, updated_at = now() WHERE alert_id = %s",
        (status, alert_id),
    )


def persist_agent_run(
    alert_id: str,
    llm_provider: str,
    model_name: Optional[str],
    started_at: datetime,
    completed_at: datetime,
    result: Optional[InvestigationResult],
    status: str,
    error_message: Optional[str],
) -> UUID:
    run_id = uuid4()
    latency_ms = int((completed_at - started_at).total_seconds() * 1000)

    db.execute(
        """
        INSERT INTO agent_runs (
            run_id, alert_id, llm_provider, model_name, started_at, completed_at,
            turn_count, tool_calls, transcript, root_cause, proposed_fix,
            confidence, status, error_message, latency_ms
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        """,
        (
            str(run_id),
            alert_id,
            llm_provider,
            model_name,
            started_at,
            completed_at,
            result.turn_count if result else None,
            orjson.dumps(result.tool_calls).decode("utf-8") if result else orjson.dumps([]).decode("utf-8"),
            orjson.dumps(result.transcript).decode("utf-8") if result else orjson.dumps([]).decode("utf-8"),
            result.root_cause if result else None,
            result.proposed_fix if result else None,
            result.confidence if result else None,
            status,
            error_message,
            latency_ms,
        ),
    )
    return run_id
