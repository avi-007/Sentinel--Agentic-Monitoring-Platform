"""Synthetic log search — no real log store backs this demo. Sampling is
seeded off the alert_id (deterministic per alert) and biased toward templates
associated with the alert's dominant_metric, so the returned "evidence"
actually points toward a plausible cause.
"""

from __future__ import annotations

import random

from ..alert_context import AlertContext
from .synthetic_data import LOG_TEMPLATES


def search_logs(ctx: AlertContext, minutes: int = 15) -> dict:
    minutes = max(1, min(int(minutes), 180))
    rng = random.Random(f"{ctx.alert_id}:search_logs")

    dominant_templates = LOG_TEMPLATES.get(ctx.dominant_metric, LOG_TEMPLATES["generic"])
    other_templates = [t for k, v in LOG_TEMPLATES.items() if k != ctx.dominant_metric for t in v]

    n_lines = rng.randint(4, 7)
    lines = []
    for _ in range(n_lines):
        # 70% chance of drawing from the dominant-metric template bank.
        pool = dominant_templates if rng.random() < 0.7 else other_templates
        template = rng.choice(pool)
        lines.append(template.format(host=ctx.host_id, service=ctx.service_name))

    lines.sort()
    return {
        "host_id": ctx.host_id,
        "service_name": ctx.service_name,
        "minutes": minutes,
        "log_lines": lines,
    }
