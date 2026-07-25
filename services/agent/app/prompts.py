"""System prompt text + OpenAI-format tool JSON schemas, shared verbatim by
both the real GPT-4o path and the mock path (the mock doesn't read these
schemas to decide what to do, but they define the contract tool_loop.py
enforces either way).
"""

from __future__ import annotations

from .alert_context import AlertContext

SYSTEM_PROMPT = """You are Sentinel, an SRE incident-response agent. You are given a single \
triggered anomaly alert for one host in a small infrastructure fleet. Your job is to investigate \
using the tools available, determine the most likely root cause, and propose a concrete, actionable fix.

Guidelines:
- Use tools to gather evidence before concluding anything. Don't guess without evidence.
- query_recent_metrics gives you real recent telemetry for the host.
- search_logs, fetch_runbook, and get_deploy_history give you supporting context (logs, the \
service's runbook, and recent deploys).
- You do not need to call every tool — stop gathering evidence once you have enough to form a \
confident hypothesis, but do not skip evidence-gathering entirely.
- When you are ready, call submit_diagnosis exactly once with your root cause, a concrete proposed \
fix (specific enough that an on-call engineer could act on it immediately), and your confidence \
(0.0-1.0) in the diagnosis.
"""


def build_user_message(ctx: AlertContext) -> str:
    return (
        f"Alert {ctx.alert_id} triggered on host `{ctx.host_id}` (service: {ctx.service_name}).\n"
        f"Severity: {ctx.severity}\n"
        f"Triggered at: {ctx.triggered_at}\n"
        f"Anomaly score: {ctx.raw_score:.3f} (dynamic threshold: {ctx.threshold:.3f})\n"
        f"Metric snapshot at trigger time: {ctx.metric_snapshot}\n\n"
        "Investigate this alert and determine the likely root cause and a concrete fix."
    )


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "query_recent_metrics",
            "description": "Fetch recent raw telemetry + anomaly scores for the alerting host from Sentinel's own metrics store.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "integer",
                        "description": "How many minutes of recent metric history to fetch (default 15, max 180).",
                        "default": 15,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": "Search recent application/system logs for the alerting host and service.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "integer",
                        "description": "How many minutes of recent logs to search (default 15, max 180).",
                        "default": 15,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_runbook",
            "description": "Fetch the operational runbook for the alerting host's service.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_deploy_history",
            "description": "Fetch recent deploy history for the alerting host's service.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "integer",
                        "description": "How many minutes back to check for deploys (default 60, max 360).",
                        "default": 60,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_diagnosis",
            "description": "Submit your final root-cause diagnosis and proposed fix. Call this exactly once, when you are done investigating.",
            "parameters": {
                "type": "object",
                "properties": {
                    "root_cause": {
                        "type": "string",
                        "description": "The most likely root cause of this alert, grounded in the evidence you gathered.",
                    },
                    "proposed_fix": {
                        "type": "string",
                        "description": "A concrete, actionable remediation an on-call engineer could execute immediately.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Your confidence in this diagnosis, from 0.0 to 1.0.",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "severity_assessment": {
                        "type": "string",
                        "description": "Your own assessment of incident severity.",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                },
                "required": ["root_cause", "proposed_fix", "confidence"],
            },
        },
    },
]

TERMINAL_TOOL_NAME = "submit_diagnosis"
