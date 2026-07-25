"""Synthetic deploy history — no real CI/CD system backs this demo. Whether a
deploy "happened" recently is a deterministic coin-flip seeded by alert_id, so
the LLM sometimes correctly implicates a deploy and sometimes correctly rules
one out (rather than a deploy always being the answer, which would make the
investigation trivial and uninteresting).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from ..alert_context import AlertContext
from .synthetic_data import DEPLOY_AUTHORS, DEPLOY_COMPONENTS


def get_deploy_history(ctx: AlertContext, minutes: int = 60) -> dict:
    minutes = max(1, min(int(minutes), 360))
    rng = random.Random(f"{ctx.alert_id}:get_deploy_history")

    triggered_at = datetime.fromisoformat(ctx.triggered_at)
    deploys = []

    # ~40% of alerts have a recent deploy in the window; biased slightly higher
    # when the dominant metric is one commonly caused by bad rollouts.
    deploy_prone = ctx.dominant_metric in ("latency_ms", "error_rate_pct")
    deploy_chance = 0.5 if deploy_prone else 0.3
    if rng.random() < deploy_chance:
        minutes_before = rng.uniform(1, minutes)
        deploy_time = triggered_at - timedelta(minutes=minutes_before)
        deploys.append(
            {
                "deploy_id": f"dep-{rng.randint(10000, 99999)}",
                "git_sha": "".join(rng.choices("0123456789abcdef", k=7)),
                "author": rng.choice(DEPLOY_AUTHORS),
                "component": rng.choice(DEPLOY_COMPONENTS),
                "deployed_at": deploy_time.isoformat(),
                "minutes_before_alert": round(minutes_before, 1),
            }
        )

    return {
        "host_id": ctx.host_id,
        "service_name": ctx.service_name,
        "minutes": minutes,
        "deploy_count": len(deploys),
        "deploys": deploys,
    }
