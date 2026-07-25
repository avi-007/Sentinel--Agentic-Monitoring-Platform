from .fetch_runbook import fetch_runbook
from .get_deploy_history import get_deploy_history
from .query_recent_metrics import query_recent_metrics
from .search_logs import search_logs

# Dispatch table keyed by the tool name exposed to the LLM. submit_diagnosis is
# deliberately not registered here — it's a terminal signal handled directly
# by tool_loop.py, not a "real" tool with a side effect.
TOOL_FUNCTIONS = {
    "query_recent_metrics": query_recent_metrics,
    "search_logs": search_logs,
    "fetch_runbook": fetch_runbook,
    "get_deploy_history": get_deploy_history,
}

__all__ = ["TOOL_FUNCTIONS"]
