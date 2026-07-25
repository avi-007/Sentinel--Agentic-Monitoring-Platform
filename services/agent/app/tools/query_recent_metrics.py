"""The one tool backed by genuine data: queries the detector's own Postgres
`metrics` table for the alerting host's recent history.
"""

from __future__ import annotations

from common import db

from ..alert_context import AlertContext


def query_recent_metrics(ctx: AlertContext, minutes: int = 15) -> dict:
    minutes = max(1, min(int(minutes), 180))
    rows = db.fetch_all(
        """
        SELECT ts, cpu_pct, mem_pct, latency_ms, error_rate_pct,
               raw_score, threshold, is_anomaly, severity
        FROM metrics
        WHERE host_id = %s AND ts >= now() - (%s * interval '1 minute')
        ORDER BY ts DESC
        LIMIT 200
        """,
        (ctx.host_id, minutes),
    )
    for row in rows:
        row["ts"] = row["ts"].isoformat()
    return {
        "host_id": ctx.host_id,
        "minutes": minutes,
        "sample_count": len(rows),
        "rows": rows,
    }
