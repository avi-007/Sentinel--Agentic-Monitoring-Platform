"""LLM_PROVIDER switch: OpenAIClient (real GPT-4o) and MockLLMClient (free,
deterministic) both implement the same small protocol, so tool_loop.py has no
idea which one it's talking to.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Optional, Protocol

import structlog

from .prompts import TERMINAL_TOOL_NAME
from .tools.synthetic_data import LOG_TEMPLATES

log = structlog.get_logger(__name__)


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict


@dataclass
class CompletionResult:
    content: Optional[str]
    tool_calls: list[ToolCallRequest] = field(default_factory=list)


class LLMClient(Protocol):
    def create_completion(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_calls_so_far: list[dict],
        force_tool: Optional[str] = None,
    ) -> CompletionResult: ...


class OpenAIClient:
    """Thin wrapper over the raw OpenAI SDK's chat.completions.create with
    function calling. tool_calls_so_far is unused here — the full history is
    already encoded in `messages`; it exists only so MockLLMClient (which
    shares this interface) has an easy structured view of prior tool results.

    Also used for OpenRouter (base_url override): OpenRouter's API is
    OpenAI-compatible, so no separate client is needed.
    """

    def __init__(self, api_key: str, model: str, timeout_seconds: float, base_url: Optional[str] = None):
        from openai import OpenAI  # imported lazily so mock-only runs don't need the package configured

        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds, base_url=base_url)
        self.model = model

    def create_completion(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_calls_so_far: list[dict],
        force_tool: Optional[str] = None,
    ) -> CompletionResult:
        kwargs: dict = {"model": self.model, "messages": messages, "tools": tools}
        kwargs["tool_choice"] = (
            {"type": "function", "function": {"name": force_tool}} if force_tool else "auto"
        )
        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        tool_calls = []
        for tc in message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCallRequest(id=tc.id, name=tc.function.name, arguments=args))

        return CompletionResult(content=message.content, tool_calls=tool_calls)


class MockLLMClient:
    """Deterministic, zero-cost stand-in for GPT-4o. Walks a fixed tool-call
    script (query_recent_metrics -> search_logs -> get_deploy_history ->
    fetch_runbook), then derives a root cause / fix from whatever those tools
    actually returned and calls submit_diagnosis — exercising exactly the same
    tool_loop.py code path a real model would.
    """

    _SCRIPT = ["query_recent_metrics", "search_logs", "get_deploy_history", "fetch_runbook"]

    def __init__(self, seed: int = 42):
        self._seed = seed

    def create_completion(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_calls_so_far: list[dict],
        force_tool: Optional[str] = None,
    ) -> CompletionResult:
        step = len(tool_calls_so_far)

        if force_tool == TERMINAL_TOOL_NAME or step >= len(self._SCRIPT):
            args = self._derive_diagnosis(tool_calls_so_far)
            return CompletionResult(
                content=None,
                tool_calls=[ToolCallRequest(id=f"mock-{step}", name=TERMINAL_TOOL_NAME, arguments=args)],
            )

        name = self._SCRIPT[step]
        args = {"minutes": 60} if name == "get_deploy_history" else ({} if name == "fetch_runbook" else {"minutes": 15})
        return CompletionResult(
            content=None, tool_calls=[ToolCallRequest(id=f"mock-{step}", name=name, arguments=args)]
        )

    def _derive_diagnosis(self, tool_calls_so_far: list[dict]) -> dict:
        by_name = {tc["name"]: tc["result"] for tc in tool_calls_so_far}
        rng = random.Random(self._seed + len(tool_calls_so_far))

        dominant_metric = self._infer_dominant_metric(by_name.get("query_recent_metrics"))
        deploys = (by_name.get("get_deploy_history") or {}).get("deploys", [])
        log_lines = (by_name.get("search_logs") or {}).get("log_lines", [])
        runbook = (by_name.get("fetch_runbook") or {}).get("runbook_markdown", "")

        deploy_recent = len(deploys) > 0
        matched_log = next((l for l in log_lines if self._log_matches(l, dominant_metric)), None)

        cause_by_metric = {
            "latency_ms": "elevated downstream/database latency causing request queuing",
            "error_rate_pct": "an increase in 5xx errors, likely from a failing downstream dependency",
            "cpu_pct": "CPU saturation, likely from a runaway process or contention",
            "mem_pct": "memory pressure consistent with a leak or undersized cache",
        }
        base_cause = cause_by_metric.get(dominant_metric, "an unspecified resource anomaly")

        if deploy_recent:
            dep = deploys[0]
            root_cause = (
                f"Recent deploy {dep['deploy_id']} ({dep['component']} change by {dep['author']}, "
                f"~{dep['minutes_before_alert']:.0f}m before the alert) most likely triggered {base_cause}."
            )
            proposed_fix = (
                f"Roll back deploy {dep['deploy_id']} on the {dep['component']} component and monitor "
                f"{dominant_metric} for recovery; if metrics normalize, root-cause confirmed."
            )
            confidence = round(rng.uniform(0.72, 0.92), 2)
        elif matched_log:
            root_cause = f"{base_cause.capitalize()}, corroborated by log evidence: \"{matched_log}\"."
            proposed_fix = self._fix_from_runbook(runbook, dominant_metric)
            confidence = round(rng.uniform(0.6, 0.8), 2)
        else:
            root_cause = f"Likely {base_cause}, though no deploy or matching log line was found to confirm it."
            proposed_fix = self._fix_from_runbook(runbook, dominant_metric)
            confidence = round(rng.uniform(0.45, 0.65), 2)

        return {
            "root_cause": root_cause,
            "proposed_fix": proposed_fix,
            "confidence": confidence,
            "severity_assessment": "high" if confidence > 0.75 else "medium",
        }

    @staticmethod
    def _infer_dominant_metric(query_result: Optional[dict]) -> str:
        rows = (query_result or {}).get("rows") or []
        if not rows:
            return "latency_ms"
        metrics = ["cpu_pct", "mem_pct", "latency_ms", "error_rate_pct"]
        means = {m: sum(r[m] for r in rows) / len(rows) for m in metrics}
        # Compare the most recent row against the window mean; largest
        # relative deviation wins.
        latest = rows[0]
        best_metric, best_ratio = "latency_ms", -1.0
        for m in metrics:
            if means[m] > 1e-6:
                ratio = latest[m] / means[m]
                if ratio > best_ratio:
                    best_ratio, best_metric = ratio, m
        return best_metric

    @staticmethod
    def _log_matches(line: str, dominant_metric: str) -> bool:
        templates = LOG_TEMPLATES.get(dominant_metric, [])
        # crude but sufficient: same template bank produced it if any of its
        # distinctive keywords show up in the line.
        keywords = {
            "latency_ms": ["timeout", "pool exhausted", "slow query", "gc pause", "retry storm"],
            "error_rate_pct": ["502", "exception", "circuit breaker", "5xx", "deserialization"],
            "cpu_pct": ["throttled", "runaway process", "load average", "reindex", "thread pool"],
            "mem_pct": ["memory usage", "oom", "memory leak", "eviction rate", "oomkilled"],
        }.get(dominant_metric, [])
        lowered = line.lower()
        return any(k in lowered for k in keywords) if templates else False

    @staticmethod
    def _fix_from_runbook(runbook: str, dominant_metric: str) -> str:
        first_step = next((l for l in runbook.splitlines() if l.strip().startswith("1.")), "")
        generic = {
            "latency_ms": "Investigate and clear the connection-pool/queue backlog on the affected dependency.",
            "error_rate_pct": "Check downstream dependency health and consider tripping the circuit breaker manually.",
            "cpu_pct": "Identify and kill/throttle the runaway process; consider scaling out the host group.",
            "mem_pct": "Restart the affected process to reclaim memory and investigate for a leak before next deploy.",
        }.get(dominant_metric, "Follow the service runbook's first triage step.")
        if first_step:
            return f"{generic} Runbook first step: {first_step.strip()}"
        return generic


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def build_llm_client(
    provider: str,
    openai_api_key: str,
    openai_model: str,
    timeout_seconds: float,
    mock_seed: int,
    openrouter_api_key: str = "",
    openrouter_model: str = "",
) -> LLMClient:
    if provider == "openai":
        if not openai_api_key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
        log.info("agent.llm_provider", provider="openai", model=openai_model)
        return OpenAIClient(api_key=openai_api_key, model=openai_model, timeout_seconds=timeout_seconds)
    if provider == "openrouter":
        if not openrouter_api_key:
            raise RuntimeError("LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is not set")
        log.info("agent.llm_provider", provider="openrouter", model=openrouter_model)
        return OpenAIClient(
            api_key=openrouter_api_key,
            model=openrouter_model,
            timeout_seconds=timeout_seconds,
            base_url=OPENROUTER_BASE_URL,
        )
    log.info("agent.llm_provider", provider="mock")
    return MockLLMClient(seed=mock_seed)
