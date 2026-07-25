"""Fixture banks backing the mocked tools: no real log store or deploy system
exists in this demo, so `search_logs` and `get_deploy_history` are entirely
synthetic, templated against the alert's host/service. `fetch_runbook` is a
handful of static per-service markdown snippets.
"""

# Log line templates, keyed by which metric they're thematically associated
# with — search_logs biases sampling toward the alert's dominant_metric so the
# "evidence" it returns actually points somewhere.
LOG_TEMPLATES: dict[str, list[str]] = {
    "latency_ms": [
        "{host} upstream[{service}] timeout after 5000ms waiting on downstream response",
        "{host} connection pool exhausted: 0/50 connections available, 214 requests queued",
        "{host} slow query detected on {service}: 4821ms (threshold 500ms)",
        "{host} GC pause: 1.2s stop-the-world, heap 92% utilized",
        "{host} retry storm detected: 340 retries/min against {service}-internal",
    ],
    "error_rate_pct": [
        "{host} 502 Bad Gateway returned to client, upstream {service} unreachable",
        "{host} unhandled exception in {service} request handler: NullPointerException",
        "{host} circuit breaker OPEN for downstream dependency payments-api",
        "{host} 5xx rate spike: 12.4% of last 1000 requests failed",
        "{host} deserialization error: unexpected schema version in message payload",
    ],
    "cpu_pct": [
        "{host} CPU throttled: cgroup limit reached, 98% utilization sustained",
        "{host} runaway process detected: pid 4821 consuming 340% CPU",
        "{host} load average 12.4 (4 cores) — scheduler contention warnings",
        "{host} background reindex job started on {service}, competing for CPU",
        "{host} thread pool saturated: 200/200 worker threads busy",
    ],
    "mem_pct": [
        "{host} memory usage climbing: 91% RSS, swap activity detected",
        "{host} OOM killer invoked for pid 5091 ({service}-worker)",
        "{host} possible memory leak: heap grew 40% over last hour with flat traffic",
        "{host} cache eviction rate spiking on {service}, memory pressure high",
        "{host} container restarted: OOMKilled (exit code 137)",
    ],
    "generic": [
        "{host} health check latency degraded but still passing",
        "{host} routine log rotation completed",
        "{host} config reload triggered for {service}",
        "{host} scheduled backup job running on {service}",
    ],
}

RUNBOOKS: dict[str, str] = {
    "web": (
        "# Runbook: web tier\n"
        "1. Check upstream `api` service health — web latency usually follows api latency.\n"
        "2. Verify CDN/edge cache hit rate hasn't dropped (cold cache = latency spike).\n"
        "3. Check for a recent deploy; web-tier regressions are the most common cause.\n"
        "4. If error rate is elevated, check for 5xx from upstream before assuming a web-tier bug.\n"
        "5. Escalation: #web-oncall"
    ),
    "api": (
        "# Runbook: api tier\n"
        "1. Check database connection pool saturation — the most common api latency cause.\n"
        "2. Check for a recent deploy or config change to this service.\n"
        "3. Check downstream dependency health (payments-api, auth-service).\n"
        "4. If CPU-bound, check for a runaway background job or reindex.\n"
        "5. Escalation: #api-oncall"
    ),
    "db": (
        "# Runbook: db tier\n"
        "1. Check for long-running or blocking queries.\n"
        "2. Check disk I/O and connection count against configured max_connections.\n"
        "3. Memory pressure usually means a bad query plan or missing index after a migration.\n"
        "4. Do not restart the primary without paging #db-oncall first.\n"
        "5. Escalation: #db-oncall"
    ),
    "cache": (
        "# Runbook: cache tier\n"
        "1. Check eviction rate and hit ratio — a cold cache after a restart looks like an incident.\n"
        "2. Check for a recent deploy that changed key TTLs or cache key format.\n"
        "3. Memory growth without traffic growth suggests a key-space leak.\n"
        "4. Escalation: #cache-oncall"
    ),
    "default": (
        "# Runbook: general\n"
        "1. Check recent deploys and config changes.\n"
        "2. Check upstream/downstream dependency health.\n"
        "3. Escalate to the owning team's on-call channel.\n"
    ),
}

DEPLOY_AUTHORS = ["a.chen", "j.okafor", "m.rossi", "s.patel", "t.nguyen"]
DEPLOY_COMPONENTS = ["routing", "auth-middleware", "cache-client", "query-planner", "connection-pool", "config"]
