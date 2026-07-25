"""Hand-written, provider-agnostic multi-turn tool-calling loop. No agent
framework — this is the whole thing: call the model, execute whatever tools it
asked for, feed results back, repeat until it calls the terminal
`submit_diagnosis` tool or we hit the turn cap (at which point one final turn
forces that tool so a structured result is always produced).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import orjson
import structlog

from .llm_client import LLMClient
from .prompts import SYSTEM_PROMPT, TERMINAL_TOOL_NAME, TOOL_SCHEMAS, build_user_message
from .alert_context import AlertContext

log = structlog.get_logger(__name__)

_DEFAULT_DIAGNOSIS = {
    "root_cause": "Agent did not produce a diagnosis within the allotted turns.",
    "proposed_fix": "Manual investigation required.",
    "confidence": 0.0,
    "severity_assessment": "medium",
}


@dataclass
class InvestigationResult:
    transcript: list[dict]
    tool_calls: list[dict]
    turn_count: int
    root_cause: str
    proposed_fix: str
    confidence: float
    severity_assessment: str = "medium"


def _to_openai_tool_calls(tool_calls) -> list[dict]:
    return [
        {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.name, "arguments": orjson.dumps(tc.arguments).decode("utf-8")},
        }
        for tc in tool_calls
    ]


def _execute_tool(tool_functions: dict[str, Callable], name: str, arguments: dict) -> dict:
    fn = tool_functions.get(name)
    if fn is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return fn(**arguments)
    except Exception as exc:  # noqa: BLE001 - a bad/hallucinated arg shouldn't kill the run
        log.warning("agent.tool_call_failed", tool=name, error=str(exc))
        return {"error": str(exc)}


def run_investigation(
    ctx: AlertContext,
    llm_client: LLMClient,
    tool_functions: dict[str, Callable],
    max_turns: int,
) -> InvestigationResult:
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(ctx)},
    ]
    tool_calls_so_far: list[dict] = []
    diagnosis: dict | None = None
    turn = 0

    while turn < max_turns and diagnosis is None:
        turn += 1
        completion = llm_client.create_completion(messages, TOOL_SCHEMAS, tool_calls_so_far)

        if not completion.tool_calls:
            # Model responded with plain text and no tool call — keep it in
            # the transcript and give it another turn rather than treating
            # this as terminal (only submit_diagnosis is terminal).
            messages.append({"role": "assistant", "content": completion.content or ""})
            continue

        messages.append(
            {
                "role": "assistant",
                "content": completion.content,
                "tool_calls": _to_openai_tool_calls(completion.tool_calls),
            }
        )

        for tc in completion.tool_calls:
            if tc.name == TERMINAL_TOOL_NAME:
                diagnosis = tc.arguments
                tool_result = {"status": "diagnosis received"}
            else:
                tool_result = _execute_tool(tool_functions, tc.name, tc.arguments)

            tool_calls_so_far.append(
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments, "result": tool_result}
            )
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": orjson.dumps(tool_result).decode("utf-8")}
            )

    if diagnosis is None:
        # Turn cap reached without a diagnosis — force one final turn.
        turn += 1
        completion = llm_client.create_completion(
            messages, TOOL_SCHEMAS, tool_calls_so_far, force_tool=TERMINAL_TOOL_NAME
        )
        messages.append(
            {
                "role": "assistant",
                "content": completion.content,
                "tool_calls": _to_openai_tool_calls(completion.tool_calls),
            }
        )
        for tc in completion.tool_calls:
            if tc.name == TERMINAL_TOOL_NAME:
                diagnosis = tc.arguments
            tool_result = {"status": "diagnosis received"} if tc.name == TERMINAL_TOOL_NAME else {"error": "forced turn, tool not executed"}
            tool_calls_so_far.append(
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments, "result": tool_result}
            )
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": orjson.dumps(tool_result).decode("utf-8")}
            )

    diagnosis = diagnosis or _DEFAULT_DIAGNOSIS

    return InvestigationResult(
        transcript=messages,
        tool_calls=tool_calls_so_far,
        turn_count=turn,
        root_cause=str(diagnosis.get("root_cause", "")),
        proposed_fix=str(diagnosis.get("proposed_fix", "")),
        confidence=float(diagnosis.get("confidence", 0.0)),
        severity_assessment=str(diagnosis.get("severity_assessment", "medium")),
    )
