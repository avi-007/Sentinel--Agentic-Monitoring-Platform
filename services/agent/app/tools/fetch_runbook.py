from __future__ import annotations

from ..alert_context import AlertContext
from .synthetic_data import RUNBOOKS


def fetch_runbook(ctx: AlertContext) -> dict:
    runbook = RUNBOOKS.get(ctx.service_name, RUNBOOKS["default"])
    return {"service_name": ctx.service_name, "runbook_markdown": runbook}
